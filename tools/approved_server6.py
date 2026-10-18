#!/usr/bin/env python3
"""Offline assembly of the approved six-player profile from an intact V7 base.

The Thunderstore lock supplies official package provenance, not the native
compatibility overlay. This tool preserves that separately audited V7 overlay,
ServerTools and generated MMHOOK, then adds only the two approved gameplay mods.
It never prepares or deploys a game runtime and refuses existing output paths.
"""
import argparse
import configparser
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import mods
from native_profile import CONFIG as NATIVE_CONFIG, FPTS, METADATA
from runtime import inventory, sha256, validate_mods

BASE_LOCK_SHA256 = 'e296ce3dc93152ff32b01abbbf0a58fe329fabb0c1c826ea7c3d27eb0dc7c1d0'
SOURCE_SHA256 = '48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c'
PATCHED_SHA256 = '73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07'
UNITY_SHA256 = 'fae6c04f23916263879196211ed241aee5f1f1b53ba4566bb99d4df8526cc105'
V7_FILES = {
    METADATA: '8e6bc370cf192e3f4056c07ec4992a302dbc91b2997024245d0500d6769b6a59',
    FPTS: '1d0ac76ef623cff52b7bbd624bcc22e6fa731c95826a25d1121e6ad2270a5e12',
    FPTS + '.disabled': 'ea955d050d4c5977451e109a82ba52134c388707100e71a6626fd0a2c4521949',
    'BepInEx/plugins/Rains.ServerTools/Rains.ServerTools.dll':
        '022d5abc7b9dd3cb47e2a9da6626736a343d3a48c772c6ea9267b1ba5520dd51',
    'BepInEx/plugins/MMHOOK/MMHOOK_RoR2.dll':
        'a43589bf5c4132dbad0a3f26fe8c681b8d7f9fc82d397f0cd93419a10441b3ba',
}
APPROVED = {
    'Moffein-TooManyFriends': {
        'version': '1.2.5',
        'archiveSha256': 'e0f22e173970e7972b56d91b2979966706cb7e191dfa0eea04f4618831fae8af',
        'dll': 'TooManyFriends.dll',
        'dllSha256': '54257ab10cb5d656ff80e0ed398b8e1c77eede4b7c387d43412fb0d3885a9ef9',
    },
    'Thrayonlosa-PillarRevive': {
        'version': '1.1.2',
        'archiveSha256': '94f44405487cd1f2c98530220d584a255a03d75552abd108f9c13dfcb1e74b34',
        'dll': 'PillarRevive.dll',
        'dllSha256': '801805422fadcba1877de4c22411c2debeb3a54fb58054ddfb3836916d3b2051',
    },
}
CONFIGS = {
    'BepInEx/config/dev.wildbook.toomanyfriends.cfg': '[Game]\nLobbySize = 6\n',
    'BepInEx/config/dolso.pillarrevive.cfg': '''[_Main]
Enable Mod = true
Curse Stacks = 0
Auto ping pillars = false
On Teleporter Completion Revive = false

[Blood]
Monster Credits = 0

[Design]
Monster Credits = 0

[Mass]
Monster Credits = 0

[Soul]
Monster Credits = 0
''',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_base(base):
    """Check a mod-only V7 assembly, not a live runtime with mutable config."""
    release = json.loads((base / 'release.json').read_text(encoding='utf-8'))
    actual = inventory(base)
    actual.pop('release.json')
    require(actual == release['modsInventory'], 'V7 base does not match its release inventory')
    require(sha256(base / 'mods-lock.json') == BASE_LOCK_SHA256,
            'Base must use the exact eight-package V7 source-overlay foundation lock')
    require(release.get('modLockSha256') == BASE_LOCK_SHA256, 'Base release lock digest differs')
    require(release.get('sourceSha256') == SOURCE_SHA256
            and release.get('patchedSha256') == PATCHED_SHA256,
            'Base belongs to another game or patch build')
    for relative, digest in V7_FILES.items():
        require(actual.get(relative) == digest, 'Missing or changed audited V7 component: ' + relative)
    native = json.loads((base / METADATA).read_text(encoding='utf-8'))
    require(native.get('schema') == 1
            and native.get('requiredFiles', {}).get('UnityPlayer.dll') == UNITY_SHA256
            and native.get('requiredFiles', {}).get(FPTS) == V7_FILES[FPTS]
            and {SOURCE_SHA256, PATCHED_SHA256}.issubset(native.get('acceptedRoR2Sha256', []))
            and native.get('configPath') == NATIVE_CONFIG,
            'Base lacks the matching V7 native compatibility guard')
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read_string((base / NATIVE_CONFIG).read_text(encoding='utf-8-sig'))
    require(not config.defaults(), 'Native configuration DEFAULT values are not supported')
    require(native.get('configValues'), 'Native guard must record exact symbol settings')
    for section, options in native['configValues'].items():
        for key, expected in options.items():
            require(config.has_option(section, key) and config.get(section, key) == expected,
                    'Base native config differs: ' + section + '/' + key)
    require(config.get('Cache', 'LastDownloadedGUID') == 'EEDAE5B1946F4B92AD8D6B3BD79F6C551',
            'Base native config uses another Unity symbol identity')
    overlays = release.get('localSourceOverlays', [])
    require(any(x.get('runtimeDllSha256') == V7_FILES[FPTS]
                and x.get('localPatchesSha256') ==
                '24651f9460a620a264f42e8239c6f97e352f80fd66e7da6a5de00cc6bf2a9f55'
                for x in overlays), 'Base release lacks audited local-overlay provenance')
    return release, actual


def assemble(base, lock_path, cache, output):
    base, lock_path, cache, output = map(lambda x: Path(x).absolute(), (base, lock_path, cache, output))
    require(base.is_dir() and cache.is_dir(), 'Base staging and offline archive cache must exist')
    require(not output.exists() and not output.is_symlink(), 'Output must be a new directory')
    for parent in output.parents:
        require(not parent.is_symlink(), 'Output ancestor must not be a symlink')
    resolved_output = output.resolve()
    for source in (base.resolve(), cache.resolve()):
        require(resolved_output != source and resolved_output not in source.parents
                and source not in resolved_output.parents, 'Output must not overlap base or cache')
    release, before = check_base(base)
    base_lock = json.loads((base / 'mods-lock.json').read_text(encoding='utf-8'))
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    mods.validate_lock(lock)
    require(lock['packages'][:len(base_lock['packages'])] == base_lock['packages'],
            'Existing V7 package metadata, versions and hashes must remain unchanged')
    additions = lock['packages'][len(base_lock['packages']):]
    require(len(additions) == len(APPROVED) and {x['package'] for x in additions} == set(APPROVED),
            'Lock must add exactly the two approved gameplay mods')
    approved_roots = [f'{p}-{a["version"]}' for p, a in APPROVED.items()]
    require(lock.get('roots') == base_lock['roots'] + approved_roots,
            'Root pins must preserve V7 and add only the approved exact versions')
    for item in additions:
        spec = APPROVED[item['package']]
        require(item['version'] == spec['version'] and item['sha256'] == spec['archiveSha256'],
                'Gameplay package version/hash differs from the approved archive')

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.approved-server6-', dir=output.parent) as temporary:
        work = Path(temporary)
        official, stage = work / 'official', work / 'stage'
        # No downloader is passed: missing or changed cached archives fail closed.
        # The raw tree is never promoted; its official FPTS is not the V7 overlay.
        mods.install(lock, cache, official)
        shutil.copytree(base, stage)
        for package, spec in APPROVED.items():
            relative = Path('BepInEx/plugins') / package
            require(not (stage / relative).exists(), 'Gameplay mod already exists in base')
            shutil.copytree(official / relative, stage / relative)
            require(sha256(stage / relative / spec['dll']) == spec['dllSha256'],
                    'Approved DLL digest differs after extraction')
        (stage / 'mods-lock.json').write_bytes(lock_path.read_bytes())
        for relative, content in CONFIGS.items():
            require(not (stage / relative).exists(), 'Approved config already exists in base')
            (stage / relative).write_text(content, encoding='utf-8')

        provenance = stage / 'BepInEx/provenance/approved-server-only-6'
        provenance.mkdir(parents=True)
        for item in additions:
            destination = provenance / f'{item["package"]}-{item["version"]}'
            destination.mkdir()
            with zipfile.ZipFile(mods.archive_path(cache, item)) as archive:
                for info in archive.infolist():
                    if info.filename.lower() in {'manifest.json', 'readme.md', 'changelog.md',
                                                 'license', 'license.md', 'license.txt'}:
                        (destination / info.filename).write_bytes(archive.read(info))
        profile = {
            'schema': 1, 'approvalDate': '2026-10-18',
            'assembler': 'tools/approved_server6.py', 'baseReleaseSha256': sha256(base / 'release.json'),
            'modLockSha256': sha256(stage / 'mods-lock.json'),
            'userApproved': True, 'requiresClientMods': False, 'clientCompatibilityVerified': False,
            'runtimeVerified': False, 'playerLimit': 6, 'packages': additions,
            'configSha256': {relative: sha256(stage / relative) for relative in CONFIGS},
            'nativeOverlay': 'Audited V7 FPTS source overlay, native guard, ServerTools and MMHOOK '
                             'are preserved from the supplied base; package lock alone is not runnable.',
            'acceptanceRemaining': ['Plugin initialization and semantic config check',
                                    'Vanilla Steam client connection after this assembly',
                                    'At least five independent players joining and playing',
                                    'True pillar revive with zero curse and stage cleanup',
                                    'Stage transition, final boss and long occupied run'],
        }
        (provenance / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n', encoding='utf-8')
        (stage / 'release.json').unlink()
        release['modLockSha256'] = sha256(stage / 'mods-lock.json')
        release['gameRuntimeVerified'] = False
        release['approvedServerOnlyProfile'] = {
            'name': 'approved-server-only-6', 'runtimeVerified': False, 'playerLimit': 6,
            'packages': approved_roots,
            'provenancePath': provenance.relative_to(stage).as_posix() + '/profile.json',
        }
        release['modsInventory'] = validate_mods(stage)
        require(inventory(base) == {**before, 'release.json': profile['baseReleaseSha256']},
                'Base changed during assembly')
        after = release['modsInventory']
        require({p for p, digest in before.items() if after.get(p) != digest} == {'mods-lock.json'},
                'Assembly unexpectedly changed an existing V7 file')
        (stage / 'release.json').write_text(json.dumps(release, indent=2), encoding='utf-8')
        require(not output.exists(), 'Output appeared during assembly')
        os.rename(stage, output)
    return {'output': str(output), 'modLockSha256': sha256(output / 'mods-lock.json'),
            'releaseSha256': sha256(output / 'release.json'), 'modsInventoryCount': len(after),
            'runtimeVerified': False, 'deployed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('base', 'lock', 'cache', 'output'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    try:
        result = assemble(args.base, args.lock, args.cache, args.output)
    except (OSError, ValueError, KeyError, configparser.Error, zipfile.BadZipFile) as error:
        parser.exit(1, 'Assembly failed: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
