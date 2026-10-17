#!/usr/bin/env python3
"""Pinned Thunderstore downloads and conservative, offline-capable staging (stdlib only)."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
import zipfile

API = "https://thunderstore.io/api/experimental/package"
PACK = "bbepis-BepInExPack"
MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_EXTRACT = 1024 * 1024 * 1024
ID = re.compile(r"^([A-Za-z0-9_]+)-([A-Za-z0-9_]+)-(\d+\.\d+\.\d+)$")
META = {"manifest.json", "readme.md", "changelog.md", "icon.png", "license", "license.md", "license.txt"}


class ModError(ValueError):
    pass


def identity(value):
    match = ID.fullmatch(value)
    if not match:
        raise ModError("Expected Namespace-Package-1.2.3: " + str(value))
    owner, name, version = match.groups()
    return owner + "-" + name, version


def version_key(version):
    return tuple(map(int, version.split(".")))


def fetch(url, limit=MAX_DOWNLOAD):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ModError("Only HTTPS downloads are allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "RoR2Server-lock/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                if urllib.parse.urlparse(response.url).scheme != "https":
                    raise ModError("Refusing insecure redirect")
                data = response.read(limit + 1)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    if len(data) > limit:
        raise ModError("Download exceeds size limit")
    return data


def metadata(package, version):
    owner, name = package.split("-", 1)
    result = json.loads(fetch(f"{API}/{owner}/{name}/{version}/", 4 * 1024 * 1024))
    if result.get("full_name") != f"{package}-{version}" or not result.get("is_active", True):
        raise ModError("Wrong or inactive API version: " + package)
    return result


def resolve(roots, get_metadata=metadata):
    """Exact transitive dependencies; explicit roots may supersede older requirements."""
    pins = {}
    for root in roots:
        package, version = identity(root)
        if package in pins and pins[package] != version:
            raise ModError("Conflicting root pins: " + package)
        pins[package] = version
    selected, ordered = {}, []

    def visit(spec):
        package, required = identity(spec)
        version = pins.get(package, required)
        if version_key(version) < version_key(required):
            raise ModError(f"Root pin {package}-{version} is older than dependency {spec}")
        if package in selected:
            if selected[package]["version"] != version:
                raise ModError("Dependency version conflict; add an explicit root pin: " + package)
            return
        info = get_metadata(package, version)
        dependencies = info.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise ModError("Invalid dependencies for " + package)
        item = {"package": package, "version": version, "dependencies": dependencies,
                "download_url": info["download_url"]}
        # Real BepInEx distributions have circular dependencies (GUI -> pack).
        # Mark selection before traversal so a matching cycle is co-installed.
        selected[package] = item
        for dep in dependencies:
            visit(dep)
        ordered.append(item)

    for root in roots:
        visit(root)
    return ordered


def archive_path(cache, item):
    identity(f"{item['package']}-{item['version']}")
    digest = item.get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ModError("Missing/invalid SHA256")
    return Path(cache) / (digest + ".zip")


def create_lock(roots, cache, get_metadata=metadata, downloader=fetch):
    items = resolve(roots, get_metadata)
    Path(cache).mkdir(parents=True, exist_ok=True)
    for item in items:
        data = downloader(item["download_url"])
        validate_archive_identity(data, item)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        destination = archive_path(cache, item)
        if destination.is_symlink():
            raise ModError("Cache entry is a symlink")
        destination.write_bytes(data)
    return {"schema": 1, "roots": roots, "packages": items}


def validate_archive_identity(data, item):
    """Reject truncated/error responses and packages disagreeing with API identity."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = archive.getinfo("manifest.json")
            if manifest.file_size > 1024 * 1024:
                raise ModError("Manifest exceeds size limit")
            info = json.loads(archive.read(manifest))
    except (zipfile.BadZipFile, KeyError, ValueError) as error:
        raise ModError("Invalid ZIP/manifest for " + item["package"] + ": " + str(error)) from error
    if info.get("name") != item["package"].split("-", 1)[1] or info.get("version_number") != item["version"]:
        raise ModError("Archive manifest identity mismatch: " + item["package"])


def validate_lock(lock):
    if lock.get("schema") != 1 or not isinstance(lock.get("packages"), list):
        raise ModError("Unsupported lock format")
    selected = {}
    for item in lock["packages"]:
        package, version = identity(f"{item['package']}-{item['version']}")
        archive_path(".", item)
        if package in selected:
            raise ModError("Duplicate locked package: " + package)
        selected[package] = version
    for spec in lock.get("roots", []):
        package, version = identity(spec)
        if selected.get(package) != version:
            raise ModError("Missing root: " + spec)
    for item in lock["packages"]:
        for spec in item["dependencies"]:
            package, version = identity(spec)
            if package not in selected or version_key(selected[package]) < version_key(version):
                raise ModError("Unsatisfied dependency: " + spec)


def safe_parts(info):
    # ZipInfo normalizes Windows separators and truncates NULs in filename.
    # orig_filename retains the untrusted central-directory spelling.
    name = info.orig_filename
    if "\\" in name or "\x00" in name or name.startswith("/"):
        raise ModError("Unsafe ZIP path: " + name)
    parts = PurePosixPath(name).parts
    if not parts or any(p in {".", ".."} or ":" in p or p.endswith((".", " ")) for p in parts):
        raise ModError("Unsafe ZIP path: " + name)
    if any(p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))} for p in parts):
        raise ModError("Reserved ZIP path: " + name)
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
        raise ModError("ZIP links/special files are prohibited")
    return parts


def mapped_path(package, parts):
    if len(parts) == 1 and parts[0].lower() in META:
        return None
    if package == PACK:
        if parts[0] != "BepInExPack":
            raise ModError("BepInEx pack must use explicit BepInExPack/ wrapper")
        parts = parts[1:]
        if not parts:
            return None
        if len(parts) == 1 and parts[0].lower() in {"winhttp.dll", "doorstop_config.ini", ".doorstop_version"}:
            return Path(*parts)
        if len(parts) >= 3 and parts[0] == "BepInEx" and parts[1] in {"core", "plugins", "patchers", "config", "monomod"}:
            return Path(*parts)
        raise ModError("Unexpected BepInEx pack payload: " + "/".join(parts))
    if parts[0].lower() == "bepinex":
        parts = parts[1:]
    if parts and parts[0].lower() in {"plugins", "patchers", "config", "monomod"}:
        category = parts[0].lower()
        # Config files retain their expected names. Plugins get per-package namespaces.
        return Path("BepInEx", category, *(() if category == "config" else (package,)), *parts[1:])
    if any(p.lower().endswith(".exe") for p in parts) or parts[0].lower() in {"riskofrain2_data", "risk of rain 2_data", "unityplayer.dll", "winhttp.dll", "doorstop_config.ini", "core"}:
        raise ModError("Game/loader core replacement is prohibited")
    return Path("BepInEx", "plugins", package, *parts)


def install(lock, cache, target, downloader=None):
    """Build a new tree and atomically rename it. Existing runtime trees are refused."""
    validate_lock(lock)
    target = Path(target).absolute()
    if target.exists() or target.is_symlink():
        raise ModError("Target must not exist; install into a new staging directory")
    for parent in target.parents:
        if parent.is_symlink():
            raise ModError("Target ancestor is a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".mods-", dir=target.parent))
    seen, total = {}, 0
    try:
        for item in lock["packages"]:
            source = archive_path(cache, item)
            if source.is_symlink():
                raise ModError("Cache entry is a symlink")
            if not source.exists():
                if downloader is None:
                    raise ModError("Missing archive (offline): " + str(source))
                data = downloader(item["download_url"])
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ModError("SHA256 mismatch: " + item["package"])
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(data)
            if source.stat().st_size > MAX_DOWNLOAD:
                raise ModError("Archive exceeds size limit")
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ModError("SHA256 mismatch: " + item["package"])
            with zipfile.ZipFile(source) as archive:
                if len(archive.infolist()) > 20000:
                    raise ModError("Too many archive entries")
                for info in archive.infolist():
                    parts = safe_parts(info)
                    if info.is_dir():
                        continue
                    total += info.file_size
                    if total > MAX_EXTRACT:
                        raise ModError("Expanded ZIP size limit exceeded")
                    relative = mapped_path(item["package"], parts)
                    if relative is None:
                        continue
                    key = relative.as_posix().casefold()
                    if key in seen:
                        raise ModError("Conflicting files: " + str(relative))
                    seen[key] = item["package"]
                    destination = work / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as incoming, destination.open("xb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
        (work / "mods-lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        os.rename(work, target)
    finally:
        if work.exists():
            shutil.rmtree(work)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("lock", help="Resolve explicit versions, download and hash archives")
    make.add_argument("--package", action="append", required=True)
    make.add_argument("--lock", required=True)
    make.add_argument("--cache", required=True)
    stage = commands.add_parser("install", help="Install locked archives into a NEW staging directory")
    stage.add_argument("--lock", required=True)
    stage.add_argument("--cache", required=True)
    stage.add_argument("--target", required=True)
    stage.add_argument("--download", action="store_true", help="Fetch missing archives; hashes remain mandatory")
    args = parser.parse_args(argv)
    try:
        if args.command == "lock":
            lock = create_lock(args.package, args.cache)
            path = Path(args.lock)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents silently replacing the production lock.
            with path.open("x", encoding="utf-8") as output:
                json.dump(lock, output, indent=2)
                output.write("\n")
        else:
            lock = json.loads(Path(args.lock).read_text(encoding="utf-8"))
            install(lock, args.cache, args.target, fetch if args.download else None)
        return 0
    except (ModError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print("mods: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
