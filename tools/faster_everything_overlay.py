#!/usr/bin/env python3
"""Offline addition of the approved Faster Everything 0.1.1 server profile.

Preserves the exact deployed six-player/headless-ping staging. Never downloads,
patches game files, deploys, or accepts an existing output directory.
"""
import argparse
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import mods
from runtime import inventory, sha256, validate_mods

BASE_RELEASE_SHA256 = 'a1b8385f5b0c51a734f5e8b6cbe0c4c175f843259f71b8ac3d9b6205a640f8f2'
PACKAGE = 'Pyroglaive-Faster_Everything'
VERSION = '0.1.1'
ARCHIVE_SHA256 = '9c438bd063adf211a586f9935b347a5bcbd632ae3fd2569ca1963e69a4152cf1'
DLL_SHA256 = '9e2a151edc5a86868c4ea88d795c2f1593674556f689936bc3fe62697a390eba'
DLL_MEMBER = 'plugins/FasterEverything/FasterEverything.dll'
PLUGIN = 'BepInEx/plugins/Pyroglaive-Faster_Everything/FasterEverything.dll'
CONFIG = 'BepInEx/config/local.ror2.fastereverything.cfg'
PROVENANCE = 'BepInEx/provenance/faster-everything-0.1.1'
FEATURES = ('Printers', 'Scrappers', 'Chance shrines', 'Blood shrines',
            'Healing shrines', 'Cauldrons', 'Cleansing pools', 'Chests')
DEPENDENCIES = ['bbepis-BepInExPack-5.4.2122', 'RiskofThunder-RoR2BepInExPack-1.43.0']
PACKAGE_ENTRY = {
    'package': PACKAGE, 'version': VERSION, 'dependencies': DEPENDENCIES,
    'download_url': 'https://thunderstore.io/package/download/Pyroglaive/Faster_Everything/0.1.1/',
    'sha256': ARCHIVE_SHA256,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def assemble(base, archive, lock, config, output):
    base, archive, lock, config, output = (Path(x).absolute() for x in (base, archive, lock, config, output))
    require(not output.exists() and not output.is_symlink(), 'Output must be a new directory')
    require(not any(parent.is_symlink() for parent in output.parents), 'Output ancestor must not be a symlink')
    require(base.is_dir(), 'Base staging does not exist')
    for source in (base, archive, lock, config):
        require(source.resolve() != output.resolve() and source.resolve() not in output.resolve().parents
                and output.resolve() not in source.resolve().parents, 'Output must not overlap an input')
    before = inventory(base)
    require(before.pop('release.json') == BASE_RELEASE_SHA256, 'Base is not the exact deployed release')
    release = json.loads((base / 'release.json').read_text(encoding='utf-8'))
    require(before == release['modsInventory'], 'Base inventory differs from release')
    require(release.get('modLockSha256') == before.get('mods-lock.json'), 'Base lock metadata differs')
    require(not any(Path(name).name.casefold() == 'fastereverything.dll' for name in before),
            'Duplicate Faster Everything DLL in base')
    require(not (base / CONFIG).exists() and not (base / PROVENANCE).exists(), 'Overlay already exists')

    base_lock = json.loads((base / 'mods-lock.json').read_text(encoding='utf-8'))
    lock_bytes = lock.read_bytes()
    selected_lock = json.loads(lock_bytes)
    mods.validate_lock(selected_lock)
    require(not any(item['package'] == PACKAGE for item in base_lock['packages']), 'Package already locked')
    expected_lock = dict(base_lock)
    expected_lock['roots'] = base_lock['roots'] + [PACKAGE + '-' + VERSION]
    expected_lock['packages'] = base_lock['packages'] + [PACKAGE_ENTRY]
    require(selected_lock == expected_lock, 'Lock must preserve all old pins and add only the approved package')
    for dependency in DEPENDENCIES:
        package, minimum = mods.identity(dependency)
        require(any(item['package'] == package and mods.version_key(item['version']) >= mods.version_key(minimum)
                    for item in base_lock['packages']), 'Base lacks a required dependency: ' + dependency)

    config_bytes = config.read_bytes()
    settings = configparser.ConfigParser(interpolation=None)
    settings.optionxform = str
    settings.read_string(config_bytes.decode('utf-8-sig'))
    require(not settings.defaults() and set(settings.sections()) == {'Timing', 'Features'}, 'Unexpected config sections')
    require(set(settings['Timing']) == {'Maximum delay'} and settings.getfloat('Timing', 'Maximum delay') == 0.1,
            'Expected maximum delay of 0.1 seconds')
    require(set(settings['Features']) == set(FEATURES)
            and all(settings.getboolean('Features', name) for name in FEATURES), 'All approved features must be enabled')

    archive_bytes = archive.read_bytes()
    require(hashlib.sha256(archive_bytes).hexdigest() == ARCHIVE_SHA256, 'Archive digest differs from the official reviewed package')
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as package_zip:
        names = package_zip.namelist()
        require(len(names) == len(set(name.casefold() for name in names)), 'Duplicate archive members')
        require([name for name in names if name.lower().endswith('.dll')] == [DLL_MEMBER], 'Unexpected package DLL layout')
        manifest = json.loads(package_zip.read('manifest.json'))
        require(manifest.get('name') == 'Faster_Everything' and manifest.get('version_number') == VERSION
                and manifest.get('dependencies') == DEPENDENCIES, 'Package identity or dependency metadata differs')
        dll = package_zip.read(DLL_MEMBER)
        require(hashlib.sha256(dll).hexdigest() == DLL_SHA256, 'Official DLL digest differs')
        documents = {name: package_zip.read(name) for name in
                     ('manifest.json', 'README.md', 'CHANGELOG.md', 'LICENSE', 'corresponding-source.zip')}

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.faster-everything-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'stage'
        shutil.copytree(base, stage)
        destination = stage / PLUGIN
        destination.parent.mkdir(parents=True)
        destination.write_bytes(dll)
        (stage / CONFIG).write_bytes(config_bytes)
        (stage / 'mods-lock.json').write_bytes(lock_bytes)
        provenance = stage / PROVENANCE
        provenance.mkdir(parents=True)
        for name, content in documents.items():
            (provenance / name).write_bytes(content)
        profile = {
            'schema': 1, 'approvalDate': '2026-10-18', 'assembler': 'tools/faster_everything_overlay.py',
            'baseReleaseSha256': BASE_RELEASE_SHA256, 'package': PACKAGE_ENTRY,
            'assemblySha256': DLL_SHA256, 'configSha256': sha256(stage / CONFIG),
            'userApproved': True, 'requiresClientMods': False, 'runtimeVerified': False,
            'clientCompatibilityVerified': False, 'maximumDelaySeconds': 0.1,
            'enabledFeatures': list(FEATURES),
            'limitations': ['Author tested isolated headless startup on Steam build 25475991; multiplayer was not verified',
                            'Vanilla clients may retain original animation timing',
                            'Router startup and actual interaction timing require separate runtime validation'],
        }
        (provenance / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n', encoding='utf-8')
        (stage / 'release.json').unlink()
        release['gameRuntimeVerified'] = False
        release['modLockSha256'] = sha256(stage / 'mods-lock.json')
        release['fasterEverythingProfile'] = profile
        after = validate_mods(stage)
        require({name for name, old in before.items() if after.get(name) != old} == {'mods-lock.json'},
                'An unrelated existing file changed')
        release['modsInventory'] = after
        require(inventory(base) == {**before, 'release.json': BASE_RELEASE_SHA256}, 'Base changed during assembly')
        (stage / 'release.json').write_text(json.dumps(release, indent=2), encoding='utf-8')
        require(not output.exists(), 'Output appeared during assembly')
        os.rename(stage, output)
    delta = sorted(set(after) - set(before) | {'mods-lock.json', 'release.json'})
    return {'output': str(output), 'assemblySha256': DLL_SHA256, 'archiveSha256': ARCHIVE_SHA256,
            'releaseSha256': sha256(output / 'release.json'), 'modLockSha256': sha256(output / 'mods-lock.json'),
            'preservedFileCount': len(before) - 1, 'deltaFiles': delta, 'runtimeVerified': False, 'deployed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'archive', 'lock', 'config', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = assemble(args.base, args.archive, args.lock, args.config, args.output)
    except (OSError, ValueError, KeyError, configparser.Error, zipfile.BadZipFile) as error:
        parser.exit(1, 'Assembly failed: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
