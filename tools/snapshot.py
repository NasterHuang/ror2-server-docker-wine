#!/usr/bin/env python3
"""Export a clean owned Steam game snapshot, leaving the installed client untouched."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

from runtime import inventory, atomic_json, MANAGED

ROOT_FILES = {'Risk of Rain 2.exe', 'UnityPlayer.dll', 'UnityCrashHandler64.exe', 'steam_api64.dll'}
ROOT_DIRS = {'Risk of Rain 2_Data', 'MonoBleedingEdge'}


def snapshot(game, target, steam_manifest):
    game, target, steam_manifest = Path(game), Path(target), Path(steam_manifest)
    if target.exists():
        raise ValueError('Snapshot target must not exist')
    manifest_text = steam_manifest.read_text(encoding='utf-8-sig')
    def field(key):
        m = re.search(r'"' + re.escape(key) + r'"\s*"([^"\r\n]*)"', manifest_text, re.I)
        return m[1] if m else None
    build = field('buildid')
    if field('appid') != '632360' or field('StateFlags') != '4' or not build:
        raise ValueError('Steam must finish updating and validating app 632360 first (StateFlags=4)')
    if field('TargetBuildID') and field('TargetBuildID') != build:
        raise ValueError('Steam update is still pending')
    for name in ROOT_FILES | ROOT_DIRS:
        if not (game / name).exists():
            raise ValueError(f'Missing required original game item: {name}')
    stage = target.parent / (target.name + '.staging-' + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    try:
        before = {name: inventory(game / name) for name in ROOT_DIRS}
        from runtime import sha256
        root_before = {name: sha256(game / name) for name in ROOT_FILES}
        for name in ROOT_DIRS:
            shutil.copytree(game / name, stage / name)
        for name in ROOT_FILES:
            shutil.copy2(game / name, stage / name)
        # Never import old patcher backups or symbols from a previously modified install.
        if list(stage.rglob('*.bak')):
            raise ValueError('Backups found in game data; use a Steam-validated original directory')
        if steam_manifest.read_text(encoding='utf-8-sig') != manifest_text:
            raise ValueError('Steam manifest changed while exporting')
        for name in ROOT_DIRS:
            if inventory(stage / name) != before[name] or inventory(game / name) != before[name]:
                raise ValueError('Game files changed during export')
        if any(sha256(stage / name) != value or sha256(game / name) != value for name, value in root_before.items()):
            raise ValueError('Game root files changed during export')
        atomic_json(stage / 'game-source.json', {'steamAppId': 632360, 'steamBuildId': build,
                    'sourceDllSha256': sha256(stage / MANAGED), 'steamFileIntegrityVerifiedByTool': False,
                    'note': 'Steam completion checked; original integrity still depends on Steam validation.'})
        stage.rename(target)
        return {'buildId': build, 'bytes': sum(p.stat().st_size for p in target.rglob('*') if p.is_file()),
                'sourceDllSha256': sha256(target / MANAGED)}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--steam-manifest', required=True)
    a = p.parse_args()
    try:
        print(json.dumps(snapshot(a.game, a.target, a.steam_manifest), indent=2))
    except (OSError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
