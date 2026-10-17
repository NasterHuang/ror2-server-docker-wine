#!/usr/bin/env python3
"""Probe the installed game's genuine Steam SDK without exposing native log IDs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def probe(game_root):
    if sys.platform != 'win32':
        raise ValueError('This client probe requires Windows')
    root = Path(game_root).resolve()
    if not (root / 'steam_api64.dll').is_file():
        raise ValueError('Game root must contain the original steam_api64.dll')
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                             '--game-root', str(root), '--worker'],
                            capture_output=True, text=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    # Native Steam logging can contain account identifiers. Return only our
    # own booleans, never relay stdout/stderr from the SDK subprocess.
    for line in result.stdout.splitlines():
        if line.startswith('RAINS_STEAM_PROBE='):
            value = json.loads(line.split('=', 1)[1])
            if set(value) == {'steamRunning', 'steamApiInitialized'} and all(type(x) is bool for x in value.values()):
                return value
    raise ValueError('Steam SDK probe failed without a valid result')


def worker(game_root):
    import ctypes
    root = Path(game_root).resolve()
    os.chdir(root)
    os.environ['SteamAppId'] = os.environ['SteamGameId'] = '632360'
    sdk = ctypes.WinDLL(str(root / 'steam_api64.dll'))
    sdk.SteamAPI_IsSteamRunning.restype = ctypes.c_bool
    sdk.SteamAPI_Init.restype = ctypes.c_bool
    running = sdk.SteamAPI_IsSteamRunning()
    initialized = sdk.SteamAPI_Init()
    if initialized:
        sdk.SteamAPI_Shutdown()
    print('RAINS_STEAM_PROBE=' + json.dumps({'steamRunning': running, 'steamApiInitialized': initialized}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root', required=True)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.worker:
            worker(args.game_root)
        else:
            result = probe(args.game_root)
            print(json.dumps(result))
            sys.exit(0 if all(result.values()) else 1)
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Steam probe could not complete; no client was launched.', file=sys.stderr)
        sys.exit(1)
