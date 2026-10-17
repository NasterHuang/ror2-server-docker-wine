#!/usr/bin/env python3
"""Transactional game staging and a bounded Wine/Xvfb supervisor (Python stdlib)."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import uuid

# Also support test harnesses that load this module directly by file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_profile import validate_native_profile
from a2s_fields import parse_info

MANAGED = Path('Risk of Rain 2_Data/Managed/RoR2.dll')
EXE = 'Risk of Rain 2.exe'
GENERATED_STATE = {'Mods/enabled_mods.txt', 'Risk of Rain 2_Data/StreamingAssets/ConVarNames.txt', 'config/config.vdf'}


def generated_state(rel):
    # Steam's native server SDK creates a data cache and flat text logs in its cwd.
    # Never allow an executable/plugin solely because it was placed in a log directory.
    parts = rel.split('/')
    return rel in GENERATED_STATE or (len(parts) == 2 and parts[0] == 'logs' and parts[1].endswith('.txt'))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def integer(env, key, default, minimum, maximum):
    raw = env.get(key, str(default))
    if not re.fullmatch(r'[0-9]+', raw):
        raise ValueError(f'{key} must be an integer')
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f'{key} must be within {minimum}..{maximum}')
    return value


def quoted(env, key, default=''):
    value = env.get(key, default)
    # Console commands use semicolon/newline separators. Reject instead of guessing escapes.
    if len(value) > 200 or any(c in value for c in '\\";\r\n\x00') or any(ord(c) < 32 for c in value):
        raise ValueError(f'{key} contains unsupported console characters')
    return '"' + value + '"'


def configuration(env):
    ports = [integer(env, k, d, 1024, 65535) for k, d in
             [('PORT', 27015), ('STEAM_QUERY_PORT', 27016), ('STEAM_SERVER_PORT', 27017)]]
    if len(set(ports)) != 3:
        raise ValueError('Game, query and Steam ports must be distinct and fixed')
    mode = env.get('GAMEMODE', 'ClassicRun')
    if mode not in ('ClassicRun', 'WeeklyRun', 'EclipseRun', 'InfiniteTowerRun'):
        raise ValueError('Unsupported GAMEMODE')
    lines = [f'sv_maxplayers {integer(env, "MAX_PLAYERS", 4, 1, 16)};',
             f'steam_server_heartbeat_enabled {integer(env, "STEAM_HEARTBEAT", 1, 0, 1)};',
             f'sv_hostname {quoted(env, "SERVER_HOSTNAME", "RoR2 private server")};',
             f'sv_port {ports[0]};', f'steam_server_query_port {ports[1]};',
             f'steam_server_steam_port {ports[2]};',
             f'sv_password {quoted(env, "SERVER_PASSWORD")};',
             f'sv_custom_tags {quoted(env, "SERVER_CUSTOM_TAGS")};',
             f'gamemode {mode};', 'vsync_count 0;', 'fps_max 60;',
             'steam_p2p_use_steam_server 1;', 'host 1;']
    return '\n'.join(lines) + '\n'


def extra_args(env):
    values = json.loads(env.get('EXTRA_ARGS_JSON', '[]'))
    if not isinstance(values, list) or any(not isinstance(v, str) or '\x00' in v for v in values):
        raise ValueError('EXTRA_ARGS_JSON must be a JSON array of strings')
    # Core lifecycle/log/config switches must not be silently overridden.
    if any(v.lower() in ('-logfile', '-executeMethod'.lower(), '-batchmode', '-nographics') or
           v.startswith('+') for v in values):
        raise ValueError('EXTRA_ARGS_JSON cannot override managed launch or console commands')
    return values


def inventory(root):
    """Hash every regular file; reject links and case collisions for Windows consistency."""
    root = Path(root)
    entries, names = {}, set()
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError(f'Symlink in input tree: {p.relative_to(root)}')
        if not p.is_file():
            if not p.is_dir():
                raise ValueError('Special file in input tree')
            continue
        rel = p.relative_to(root).as_posix()
        if rel.casefold() in names:
            raise ValueError(f'Case collision: {rel}')
        names.add(rel.casefold())
        entries[rel] = sha256(p)
    return entries


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def validate_mods(mods):
    inv = inventory(mods)
    if not inv:
        raise ValueError('MODS_ENABLED=1 but /mods is empty')
    for rel in inv:
        folded = rel.casefold()
        if not (folded.startswith('bepinex/') or folded in
                ('winhttp.dll', 'doorstop_config.ini', '.doorstop_version', 'mods-lock.json')):
            raise ValueError(f'Mod staging may not replace game files: {rel}')
    for required in ('winhttp.dll', 'doorstop_config.ini', 'BepInEx/core/BepInEx.Preloader.dll'):
        if required not in inv:
            raise ValueError(f'Missing Windows Mono loader file: {required}')
    return inv


def recover_interrupted_promotion(data):
    data = Path(data)
    current, previous = data / 'runtime', data / 'previous'
    if current.is_symlink() or previous.is_symlink():
        raise ValueError('Runtime promotion paths must be real directories')
    if not current.exists() and previous.is_dir():
        previous.rename(current)
        return True
    return False


def validate_input_paths(source, data, mods, env):
    # Reject overlap before recovery or creating a stage: either direction can
    # recursively copy output into itself or move/delete an original input.
    output = Path(data).resolve()
    inputs = [Path(source), Path(env.get('STEAMWORKS_DIR', '/config/steamworks'))]
    if integer(env, 'MODS_ENABLED', 0, 0, 1):
        inputs.append(Path(mods))
    for input_path in inputs:
        resolved = input_path.resolve()
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError('Runtime data must not overlap source, mods or Steamworks input directories')


def prepare(source, data, mods, env, patcher):
    source, data, mods = Path(source), Path(data), Path(mods)
    validate_input_paths(source, data, mods, env)
    recover_interrupted_promotion(data)
    cfg = configuration(env)
    extra_args(env)
    if env.get('ACK_EXPERIMENTAL') != '1':
        raise ValueError('Set ACK_EXPERIMENTAL=1 only after reviewing the exact-build patch report')
    if env.get('SERVER_MODE', 'experimental') != 'experimental':
        raise ValueError('Only explicit experimental mode is implemented; latest-game compatibility is not certified')
    expected = env.get('EXPECTED_GAME_SHA256', '').lower()
    if not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('EXPECTED_GAME_SHA256 must pin the clean game DLL')
    if not (source / EXE).is_file() or not (source / MANAGED).is_file():
        raise ValueError('Mount a clean Windows Steam game copy at /source')
    if sha256(source / MANAGED) != expected:
        raise ValueError('Game SHA256 changed; re-audit before updating')
    for dirty in (source / 'BepInEx', source / 'winhttp.dll', source / (str(MANAGED) + '.bak')):
        if dirty.exists():
            raise ValueError(f'Use a clean staging copy, not an existing modded/patched game: {dirty.name}')
    manifest = Path(env.get('PATCH_MANIFEST', '/config/patch-manifest.json'))
    manifest_bytes = manifest.read_bytes()
    manifest_data = json.loads(manifest_bytes)
    if manifest_data.get('inputSha256', '').lower() != expected:
        raise ValueError('Patch manifest must pin the same clean game SHA256')
    # Do not advertise a flag-only patch as an independent-server conversion.
    if not manifest_data.get('startup') or not manifest_data.get('lobby'):
        raise ValueError('Independent-server experiment requires reviewed startup and lobby sites')
    support_dir = Path(env.get('STEAMWORKS_DIR', '/config/steamworks'))
    support_inventory = inventory(support_dir) if support_dir.exists() else {}
    support_names = {'steamclient64.dll', 'tier0_s64.dll', 'vstdlib_s64.dll'}
    if support_inventory and (not support_names.issubset(support_inventory) or
                              not set(support_inventory).issubset(support_names | {'steamwebrtc64.dll'})):
        raise ValueError('Steamworks support must contain the three Windows x64 DLLs and optionally steamwebrtc64.dll')
    if manifest_data.get('serverBootstrap') and not support_inventory:
        raise ValueError('Server bootstrap requires genuine Windows Steamworks support DLLs')
    source_inventory = inventory(source)
    mod_inventory = validate_mods(mods) if integer(env, 'MODS_ENABLED', 0, 0, 1) else {}
    data.mkdir(parents=True, exist_ok=True)
    staging = data / ('staging-' + uuid.uuid4().hex)
    try:
        shutil.copytree(source, staging)
        if inventory(staging) != source_inventory or inventory(source) != source_inventory:
            raise ValueError('Source changed during copy; stop Steam updates and retry')
        for rel, digest in support_inventory.items():
            shutil.copy2(support_dir / rel, staging / rel)
            if sha256(staging / rel) != digest:
                raise ValueError('Steamworks support changed during copy')
        # The reviewed manifest is snapshotted to eliminate concurrent file replacement.
        (staging / 'patch-manifest.json').write_bytes(manifest_bytes)
        patched = staging / 'RoR2.patched.dll'
        subprocess.run([str(patcher), '--input', str(staging / MANAGED), '--output', str(patched),
                        '--manifest', str(staging / 'patch-manifest.json'), '--report', str(staging / 'patch-report.json')], check=True)
        patched.replace(staging / MANAGED)
        if mod_inventory:
            shutil.copytree(mods, staging, dirs_exist_ok=True)
            if inventory(mods) != mod_inventory:
                raise ValueError('Mod staging changed during copy')
            for rel, digest in mod_inventory.items():
                if sha256(staging / rel) != digest:
                    raise ValueError('Mod staging changed during copy')
            if set(inventory(staging)) != (set(source_inventory) | set(mod_inventory) | set(support_inventory) |
                                            {'patch-manifest.json', 'patch-report.json'}):
                raise ValueError('Unexpected files appeared during mod copy')
        config_dir = staging / 'Risk of Rain 2_Data/Config'
        config_dir.mkdir(parents=True, exist_ok=True)
        for name in ('server_startup.cfg', 'server.cfg'):
            (config_dir / name).write_text(cfg, encoding='utf-8')
        metadata = {'sourceSha256': expected, 'sourceInventory': source_inventory,
                    'modsInventory': mod_inventory, 'supportInventory': support_inventory,
                    'patchedSha256': sha256(staging / MANAGED),
                    'patchManifestSha256': hashlib.sha256(manifest_bytes).hexdigest(),
                    'gameRuntimeVerified': False, 'createdUtc': time.time()}
        atomic_json(staging / 'release.json', metadata)
        # Keep persistent plugin config separate from package defaults.
        if mod_inventory and os.name == 'posix':
            persistent = data / 'bepinex-config'
            if not persistent.exists():
                shutil.copytree(staging / 'BepInEx/config', persistent) if (staging / 'BepInEx/config').exists() else persistent.mkdir()
            target = staging / 'BepInEx/config'
            if target.exists():
                shutil.rmtree(target)
            target.symlink_to(persistent.resolve(), target_is_directory=True)
        validate_native_profile(staging)
        previous, current = data / 'previous', data / 'runtime'
        if previous.exists():
            shutil.rmtree(previous)
        if current.exists():
            current.rename(previous)
        try:
            staging.rename(current)
        except BaseException:
            if previous.exists() and not current.exists():
                previous.rename(current)
            raise
        return current
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def a2s_info(host, port, timeout=1.5, detailed=False):
    """Bounded A2S_INFO with one challenge. This is not a multiplayer readiness test."""
    request = b'\xff\xff\xff\xffTSource Engine Query\0'
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.send(request)
        reply = sock.recv(65535)
        if reply[:5] == b'\xff\xff\xff\xffA' and len(reply) == 9:
            sock.send(request + reply[5:9])
            reply = sock.recv(65535)
    result = parse_info(reply)
    return result if detailed else {key: result[key] for key in ('name', 'map', 'appId16', 'players', 'maxPlayers')}


def verify_release(runtime, env):
    """Verify a PC-prepared release, allowing only config and generated plugin state drift."""
    runtime = Path(runtime)
    if env.get('ACK_EXPERIMENTAL') != '1' or env.get('SERVER_MODE', 'experimental') != 'experimental':
        raise ValueError('Explicit experimental acknowledgement required')
    configuration(env)
    extra_args(env)
    release = json.loads((runtime / 'release.json').read_text(encoding='utf-8'))
    expected = env.get('EXPECTED_GAME_SHA256', '').lower()
    if not re.fullmatch('[0-9a-f]{64}', expected) or release['sourceSha256'] != expected:
        raise ValueError('Prepared release source does not match expected game SHA256')
    if sha256(runtime / MANAGED) != release['patchedSha256']:
        raise ValueError('Prepared game assembly changed')
    if sha256(runtime / 'patch-manifest.json') != release['patchManifestSha256']:
        raise ValueError('Prepared patch manifest changed')
    locked = {**release['sourceInventory'], **release['modsInventory'], **release.get('supportInventory', {})}
    allowed_metadata = {'release.json', 'patch-manifest.json', 'patch-report.json'} | GENERATED_STATE
    for file in runtime.rglob('*'):
        rel = file.relative_to(runtime).as_posix()
        if file.is_symlink():
            if rel == 'BepInEx/config' and file.resolve() == (runtime.parent / 'bepinex-config').resolve():
                continue
            raise ValueError(f'Unexpected release symlink: {rel}')
        if not file.is_file() or rel in locked or rel in allowed_metadata or generated_state(rel):
            continue
        if rel.startswith(('BepInEx/config/', 'BepInEx/cache/', 'BepInEx/LogOutput', 'Risk of Rain 2_Data/Config/')):
            continue
        raise ValueError(f'Unlocked new release file: {rel}')
    for rel, digest in locked.items():
        path = Path(rel)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Invalid release inventory path')
        if rel == MANAGED.as_posix() or generated_state(rel) or rel.startswith(('Risk of Rain 2_Data/Config/', 'BepInEx/config/')):
            continue
        if sha256(runtime / rel) != digest:
            raise ValueError(f'Release file changed: {rel}')
    validate_native_profile(runtime)
    return release


def readiness(data, state, now=None):
    """Query response plus optional fresh game telemetry; never certifies multiplayer."""
    result = {'query': a2s_info('127.0.0.1', state['queryPort'], timeout=0.5),
              'multiplayerVerified': False}
    if state.get('requireGameTelemetry'):
        sample = json.loads((Path(data) / 'status/game.json').read_text(encoding='utf-8'))
        if not isinstance(sample, dict) or not isinstance(sample.get('sampleUtc'), str):
            raise ValueError('Game telemetry needs an ISO timestamp')
        stamp = datetime.datetime.fromisoformat(sample['sampleUtc'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Game telemetry timestamp must include a timezone')
        now = now or datetime.datetime.now(datetime.timezone.utc)
        age = (now - stamp).total_seconds()
        if not -5 <= age <= 30:
            raise ValueError('Game telemetry is stale or ahead of the host clock')
        if sample.get('gameLoadFinished') is not True or sample.get('serverActive') is not True:
            raise ValueError('Game initialization or host activation is incomplete')
        result['gameTelemetryFresh'] = True
        result['steamLoggedOn'] = sample.get('steamLoggedOn') is True
    return result


def supervise(runtime, data, env):
    data, runtime = Path(data), Path(runtime)
    children = []
    stopping = False
    state_path = data / 'state.json'
    # Remove stale health data before creating any child.
    state_path.unlink(missing_ok=True)

    def stop(signum, _frame):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    child_env = dict(env, DISPLAY=':99')
    if integer(env, 'MODS_ENABLED', 0, 0, 1):
        child_env['WINEDLLOVERRIDES'] = 'winhttp=n,b;mscoree,mshtml='
        child_env.pop('DOORSTOP_DISABLE', None)
    else:
        child_env['WINEDLLOVERRIDES'] = 'winhttp=b;mscoree,mshtml='
        child_env['DOORSTOP_DISABLE'] = '1'
        child_env['RAINS_SERVER_TOOLS'] = '0'
    min_free = integer(env, 'MIN_FREE_MB', 1024, 128, 65536) * 1024 * 1024
    startup_timeout = integer(env, 'STARTUP_TIMEOUT_SECONDS', 600, 30, 3600)
    try:
        (data / 'status/game.json').unlink(missing_ok=True)
        (data / 'status/boot.json').unlink(missing_ok=True)
        if shutil.disk_usage(data).free < min_free:
            raise RuntimeError('Insufficient free disk for router reserve')
        x = subprocess.Popen(['Xvfb', ':99', '-screen', '0', '640x480x24', '-nolisten', 'tcp'],
                             env=child_env, start_new_session=True)
        children.append(x)
        for _ in range(50):
            if stopping or x.poll() is not None:
                raise RuntimeError('Xvfb stopped during initialization')
            if Path('/tmp/.X11-unix/X99').exists():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError('Xvfb socket timeout')
        # No interactive winecfg. Prefix initialization belongs to Wine itself.
        command = ['wine', str(runtime / EXE), '-batchmode', '-nographics', '-logFile', '-'] + extra_args(env)
        game = subprocess.Popen(command, cwd=runtime, env=child_env, start_new_session=True)
        children.append(game)
        state = {'pid': game.pid, 'phase': 'process-running',
                 'requireGameTelemetry': bool(integer(env, 'MODS_ENABLED', 0, 0, 1)) and env.get('RAINS_SERVER_TOOLS') == '1',
                 'multiplayerVerified': False, 'queryPort': int(env.get('STEAM_QUERY_PORT', '27016'))}
        atomic_json(state_path, state)
        started = time.monotonic()
        next_probe, startup_ready = started, False
        print('Wine process started. Startup checks do not certify multiplayer.', flush=True)
        while not stopping:
            if shutil.disk_usage(data).free < min_free:
                raise RuntimeError('Disk reserve reached; stopping this game process')
            if x.poll() is not None:
                raise RuntimeError('Xvfb exited while game was running')
            result = game.poll()
            if result is not None:
                return result if result != 0 else 1  # A server that spontaneously exits must not look healthy.
            now = time.monotonic()
            if not startup_ready and now >= next_probe:
                next_probe = now + 5
                try:
                    readiness(data, state)
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                else:
                    startup_ready = True
                    state['phase'] = 'startup-checks-passed'
                    atomic_json(state_path, state)
                    print('Startup checks passed; multiplayer and Steam authentication remain separate tests.', flush=True)
            if not startup_ready and now - started >= startup_timeout:
                raise RuntimeError(f'Game startup did not pass checks within {startup_timeout}s; stopping this game process')
            time.sleep(0.5)
        return 0
    finally:
        state_path.unlink(missing_ok=True)
        # Limit cleanup to this container's dedicated Wine prefix.
        try:
            subprocess.run(['wineserver', '-k'], env=child_env, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', choices=['run', 'prepare', 'launch', 'health', 'query'], default='run')
    parser.add_argument('--source', default='/source')
    parser.add_argument('--data', default='/data')
    parser.add_argument('--mods', default='/mods')
    parser.add_argument('--patcher', default='/opt/patcher/RoR2Patcher')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=27016)
    args = parser.parse_args()
    try:
        if args.command == 'query':
            print(json.dumps(a2s_info(args.host, args.port), ensure_ascii=False))
            return 0
        if args.command == 'health':
            state = json.loads((Path(args.data) / 'state.json').read_text(encoding='utf-8'))
            os.kill(state['pid'], 0)
            print(json.dumps(readiness(args.data, state), ensure_ascii=False))
            return 0
        if args.command != 'launch':
            validate_input_paths(args.source, args.data, args.mods, os.environ)
        Path(args.data).mkdir(parents=True, exist_ok=True)
        # Host/container level lock prevents two preparers from replacing an active runtime.
        import fcntl
        with (Path(args.data) / '.runtime.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            (Path(args.data) / 'state.json').unlink(missing_ok=True)
            if args.command == 'launch':
                recover_interrupted_promotion(args.data)
                runtime = Path(args.data) / 'runtime'
                verify_release(runtime, os.environ)
                cfg_dir = runtime / 'Risk of Rain 2_Data/Config'
                for name in ('server_startup.cfg', 'server.cfg'):
                    (cfg_dir / name).write_text(configuration(os.environ), encoding='utf-8')
            else:
                runtime = prepare(args.source, args.data, args.mods, os.environ, args.patcher)
            print(f'Prepared {runtime}; actual game compatibility remains unverified.', flush=True)
            return supervise(runtime, args.data, os.environ) if args.command in ('run', 'launch') else 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
