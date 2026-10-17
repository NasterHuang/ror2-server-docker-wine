#!/usr/bin/env python3
"""Package the reviewed mod overlay and corresponding source, without game files."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

from runtime import sha256


def package(mods, cache, output):
    mods, cache, output = map(Path, (mods, cache, output))
    root = Path(__file__).resolve().parents[1]
    archive = output.parent / (output.name + '.zip')
    if output.exists() or archive.exists():
        raise ValueError('Package output must be new')
    lock = json.loads((mods / 'mods-lock.json').read_text(encoding='utf-8'))
    shutil.copytree(mods, output, ignore=shutil.ignore_patterns('release.json', 'MMHOOK', '__pycache__', 'LogOutput*', 'cache'))
    for name in ('.env', 'steam_appid.txt', 'Risk of Rain 2.exe', 'UnityPlayer.dll', 'Risk of Rain 2_Data'):
        if (output / name).exists():
            raise ValueError('A client mod package must not contain private/game runtime files')
    shutil.copy2(root / 'profiles/native/Launch-TestClient.ps1', output / 'Launch-TestClient.ps1')
    source = output / 'Sources'
    shutil.copytree(root / 'Compatibility/FixPluginTypesSerialization', source / 'FixPluginTypesSerialization',
                    ignore=shutil.ignore_patterns('bin', 'obj', '__pycache__', '.git'))
    shutil.copytree(root / 'ServerTools', source / 'Rains.ServerTools', ignore=shutil.ignore_patterns('bin', 'obj'))
    shutil.copy2(root / 'LICENSE', source / 'Rains.ServerTools/LICENSE')
    # Original pinned archives retain all upstream README/license/source notices.
    packages = source / 'ThunderstorePackages'
    packages.mkdir()
    for item in lock['packages']:
        candidate = cache / (item['sha256'] + '.zip')
        if sha256(candidate) != item['sha256']:
            raise ValueError('Original package archive missing or changed: ' + item['package'])
        shutil.copy2(candidate, packages / (item['package'] + '-' + item['version'] + '.zip'))
    (output / 'TEST-INSTRUCTIONS.txt').write_text(
        'Experimental RoR2 build 25921972 / game 1.5.0 test overlay.\n'
        '1. Copy your legitimate clean Steam game into a separate folder. Do not merge old mods.\n'
        '2. Extract this ZIP into that COPY, alongside Risk of Rain 2.exe. No game files are included.\n'
        '3. Keep Steam signed in. Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\\Launch-TestClient.ps1\n'
        '4. Disable crossplay. Open console with Ctrl+Alt+grave and enter the private address/password supplied separately.\n'
        '5. First launch regenerates MMHOOK. Keep BepInEx/LogOutput.log for this test.\n'
        'This profile has a local maintained FPTS DLL; original sources, patch recipe and package archives are in Sources.\n'
        'Visual playability, two players, WAN, stage progression and stability remain to be tested.\n', encoding='utf-8')
    # Keep the default graphical client free of batch diagnostic probes/autoexec secrets.
    if (output / 'BepInEx/plugins/Rains.ClientProbe').exists():
        raise ValueError('Diagnostic client probe must not ship in the player package')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for file in sorted(output.rglob('*')):
            if file.is_file():
                target.write(file, file.relative_to(output).as_posix())
    report = {'archive': archive.name, 'sha256': sha256(archive), 'gameFilesIncluded': False,
              'runtimeVerified': False, 'note': 'Packaging only; visual/multiplayer acceptance is pending'}
    archive.with_suffix('.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('mods', 'cache', 'output'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.mods, args.cache, args.output)))
