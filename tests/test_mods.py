import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location("mods", Path(__file__).parents[1] / "tools" / "mods.py")
mods = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mods)


def zipped(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in entries:
            if isinstance(name, str):
                entry = zipfile.ZipInfo()
                entry.filename = name  # Preserve hostile backslashes on Windows too.
                name = entry
            archive.writestr(name, value)
    return output.getvalue()


class ModTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()

    def locked(self, data, package="Example-Mod", dependencies=None):
        digest = hashlib.sha256(data).hexdigest()
        (self.cache / (digest + ".zip")).write_bytes(data)
        return {"schema": 1, "roots": [package + "-1.0.0"], "packages": [{
            "package": package, "version": "1.0.0", "sha256": digest,
            "dependencies": dependencies or [], "download_url": "https://example.invalid/mod.zip"}]}

    def test_dependency_order_and_explicit_upgrade(self):
        def get(package, version):
            return {"dependencies": ["A-Core-1.0.0"] if package == "A-Mod" else [],
                    "download_url": "https://example.invalid/a.zip"}
        result = mods.resolve(["A-Mod-1.0.0", "A-Core-2.0.0"], get)
        self.assertEqual([(i["package"], i["version"]) for i in result], [("A-Core", "2.0.0"), ("A-Mod", "1.0.0")])

    def test_conflict_fails_and_matching_cycle_is_supported(self):
        def get(package, version):
            deps = {"A-One": ["A-Core-1.0.0"], "A-Two": ["A-Core-2.0.0"]}
            return {"dependencies": deps.get(package, []), "download_url": "https://example.invalid/a.zip"}
        with self.assertRaisesRegex(mods.ModError, "conflict"):
            mods.resolve(["A-One-1.0.0", "A-Two-1.0.0"], get)
        cycle = mods.resolve(["A-One-1.0.0"], lambda p, v: {
            "dependencies": ["A-One-1.0.0"], "download_url": "https://example.invalid/a.zip"})
        self.assertEqual(len(cycle), 1)

    def test_lock_roundtrip_offline_install(self):
        data = zipped([("manifest.json", '{"name":"Mod","version_number":"1.0.0"}'),
                       ("plugins/test.dll", "hello"), ("config/test.cfg", "a=1")])
        lock = mods.create_lock(["Example-Mod-1.0.0"], self.cache,
                                lambda p, v: {"dependencies": [], "download_url": "https://example.invalid/a.zip"},
                                lambda url: data)
        target = self.root / "stage"
        mods.install(json.loads(json.dumps(lock)), self.cache, target)
        self.assertEqual((target / "BepInEx/plugins/Example-Mod/test.dll").read_text(), "hello")
        self.assertEqual((target / "BepInEx/config/test.cfg").read_text(), "a=1")
        self.assertFalse((target / "manifest.json").exists())

    def test_bepinex_wrapper(self):
        data = zipped([("BepInExPack/winhttp.dll", "loader"),
                       ("BepInExPack/BepInEx/core/BepInEx.dll", "core"), ("README.md", "docs")])
        mods.install(self.locked(data, mods.PACK), self.cache, self.root / "stage")
        self.assertEqual((self.root / "stage/winhttp.dll").read_text(), "loader")

    def test_traversal_and_special_paths_fail_atomically(self):
        for name in ("../oops", "/root.dll", "C:/oops", "plugins/../oops", "plugins\\oops", "plugins/CON.dll", "plugins/trailing./a"):
            with self.subTest(name=name):
                target = self.root / "stage"
                lock = self.locked(zipped([("ok.dll", "okay"), (name, "bad")]))
                with self.assertRaises(mods.ModError):
                    mods.install(lock, self.cache, target)
                self.assertFalse(target.exists())
                self.assertEqual(list(self.root.glob(".mods-*")), [])

    def test_symlink_archive_rejected(self):
        entry = zipfile.ZipInfo("plugins/link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(mods.ModError, "links"):
            mods.install(self.locked(zipped([(entry, "../../victim")])) , self.cache, self.root / "stage")

    def test_hash_tampering_rejected(self):
        lock = self.locked(zipped([("mod.dll", "test")]))
        mods.archive_path(self.cache, lock["packages"][0]).write_bytes(b"tampered")
        with self.assertRaisesRegex(mods.ModError, "SHA256"):
            mods.install(lock, self.cache, self.root / "stage")

    def test_missing_cache_is_offline_by_default(self):
        lock = self.locked(zipped([("mod.dll", "test")]))
        mods.archive_path(self.cache, lock["packages"][0]).unlink()
        with self.assertRaisesRegex(mods.ModError, "offline"):
            mods.install(lock, self.cache, self.root / "stage")

    def test_lock_rejects_truncated_download_and_wrong_identity(self):
        get = lambda p, v: {"dependencies": [], "download_url": "https://example.invalid/a.zip"}
        for data in (b"PK-truncated", zipped([("manifest.json", '{"name":"Wrong","version_number":"1.0.0"}')])):
            with self.assertRaises(mods.ModError):
                mods.create_lock(["Example-Mod-1.0.0"], self.cache, get, lambda url: data)

    def test_core_replacement_and_case_collision(self):
        for entries in [[("RiskOfRain2.exe", "bad")], [("UnityPlayer.dll", "bad")],
                        [("BepInEx/core/overwrite.dll", "bad")], [("mod.dll", "1"), ("MOD.dll", "2")]]:
            with self.subTest(entries=entries):
                with self.assertRaises(mods.ModError):
                    mods.install(self.locked(zipped(entries)), self.cache, self.root / "stage")

    def test_existing_runtime_not_modified(self):
        target = self.root / "runtime"
        target.mkdir()
        sentinel = target / "RiskOfRain2.exe"
        sentinel.write_text("original")
        with self.assertRaisesRegex(mods.ModError, "must not exist"):
            mods.install(self.locked(zipped([("mod.dll", "test")])), self.cache, target)
        self.assertEqual(sentinel.read_text(), "original")

    def test_missing_dependency_and_duplicate_rejected(self):
        lock = self.locked(zipped([("mod.dll", "test")]), dependencies=["A-Missing-1.0.0"])
        with self.assertRaisesRegex(mods.ModError, "Unsatisfied"):
            mods.validate_lock(lock)
        lock["packages"][0]["dependencies"] = []
        lock["packages"].append(lock["packages"][0].copy())
        with self.assertRaisesRegex(mods.ModError, "Duplicate"):
            mods.validate_lock(lock)

    def test_expanded_size_limit(self):
        lock = self.locked(zipped([("mod.dll", "12345")]))
        previous = mods.MAX_EXTRACT
        try:
            mods.MAX_EXTRACT = 4
            with self.assertRaisesRegex(mods.ModError, "size limit"):
                mods.install(lock, self.cache, self.root / "stage")
        finally:
            mods.MAX_EXTRACT = previous


if __name__ == "__main__":
    unittest.main()
