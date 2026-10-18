#!/usr/bin/env python3
"""Add reviewed headless auto-ping support and the approved Pillar settings.

Offline assembly only. Requires the intact approved six-player Mod staging,
a matching local compatibility build, and a new output directory.
"""
import argparse
import configparser
import json
import os
from pathlib import Path
import shutil
import tempfile

from approved_server6 import V7_FILES, SOURCE_SHA256, PATCHED_SHA256
from runtime import inventory, sha256, validate_mods

PILLAR = 'BepInEx/plugins/Thrayonlosa-PillarRevive/PillarRevive.dll'
PILLAR_SHA = '801805422fadcba1877de4c22411c2debeb3a54fb58054ddfb3836916d3b2051'
CONFIG = 'BepInEx/config/dolso.pillarrevive.cfg'
ASSEMBLY = 'Rains.PillarReviveHeadless.dll'
PLUGIN = 'BepInEx/plugins/Rains.PillarReviveHeadless/' + ASSEMBLY
PROVENANCE = 'BepInEx/provenance/pillarrevive-headless'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def assemble(base, build, config, output):
    base, build, config, output = (Path(x).resolve() for x in (base, build, config, output))
    require(not output.exists(), 'Output must be a new directory')
    for source in (base, build, config.parent):
        require(source != output and source not in output.parents and output not in source.parents,
                'Output must not overlap an input directory')
    require(not any(p.is_symlink() for p in base.rglob('*')), 'Base staging must not contain symlinks')
    release = json.loads((base / 'release.json').read_text(encoding='utf-8'))
    before = inventory(base)
    base_release_sha = before.pop('release.json')
    require(before == release['modsInventory'], 'Base inventory differs from release')
    require(release['sourceSha256'] == SOURCE_SHA256 and release['patchedSha256'] == PATCHED_SHA256,
            'Game build differs from the reviewed profile')
    require(release.get('approvedServerOnlyProfile', {}).get('playerLimit') == 6,
            'Base must be the approved six-player staging')
    for name, digest in {**V7_FILES, PILLAR: PILLAR_SHA}.items():
        require(before.get(name) == digest, 'Audited base component differs: ' + name)
    require(not (base / PLUGIN).exists() and not (base / PROVENANCE).exists(),
            'Headless overlay already exists in base')

    settings = configparser.ConfigParser(interpolation=None)
    settings.optionxform = str
    settings.read_string(config.read_text(encoding='utf-8-sig'))
    require(not settings.defaults(), 'Config DEFAULT values are not supported')
    require(settings.getboolean('_Main', 'On Teleporter Completion Revive')
            and settings.getboolean('_Main', 'Auto ping pillars')
            and settings.getint('_Main', 'Curse Stacks') == 0,
            'Expected both requested options enabled and zero curse')
    require(all(settings.getfloat(section, 'Monster Credits') == 0
                for section in ('Blood', 'Design', 'Mass', 'Soul')),
            'Keep the approved zero extra monster credits')

    report = json.loads((build / 'build.json').read_text(encoding='utf-8'))
    digest = sha256(build / ASSEMBLY)
    require(report['assemblySha256'] == digest, 'Compatibility build digest differs')
    sources = report['sourceFilesSha256']
    require(sources and all(isinstance(k, str) and isinstance(v, str) for k, v in sources.items()),
            'Build must include source digests')
    workspace = Path(__file__).resolve().parents[1]
    source_root = workspace / 'Compatibility/PillarReviveHeadless'
    require(source_root.is_dir(), 'Compatibility sources are absent')
    for name, expected in sources.items():
        source = (workspace / name).resolve()
        require(source.is_relative_to(source_root) and source.is_file(), 'Unexpected build source path')
        require(sha256(source) == expected, 'Compatibility source changed since build: ' + name)
    require(any(Path(name).name == 'Plugin.cs' for name in sources), 'Plugin source digest missing')

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pillar-headless-', dir=output.parent) as temporary:
        work = Path(temporary).resolve()
        require(work.is_relative_to(output.parent), 'Temporary workspace escaped output parent')
        stage = work / 'stage'
        shutil.copytree(base, stage)
        destination = stage / PLUGIN
        destination.parent.mkdir(parents=True)
        shutil.copy2(build / ASSEMBLY, destination)
        (stage / CONFIG).write_bytes(config.read_bytes())
        provenance = stage / PROVENANCE
        provenance.mkdir(parents=True)
        shutil.copy2(build / 'build.json', provenance / 'build.json')
        for name in sources:
            relative = (workspace / name).resolve().relative_to(source_root)
            source_copy = provenance / 'source' / relative
            source_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workspace / name, source_copy)
        profile = {
            'schema': 1, 'approvalDate': '2026-10-18', 'baseReleaseSha256': base_release_sha,
            'assemblySha256': digest, 'officialPillarSha256': PILLAR_SHA,
            'configSha256': sha256(stage / CONFIG), 'requiresClientMods': False,
            'runtimeVerified': False, 'onTeleporterCompletionRevive': True, 'autoPingPillars': True,
            'scope': 'Headless PingPillar replacement only; no Boss-zone or revive-mechanics changes',
            'limitations': ['Actual teammate marker display still needs a real multiplayer test',
                            'Victim authority owner does not render its own server-originated marker',
                            'Late joiners are not guaranteed to see a previous marker'],
        }
        (provenance / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n', encoding='utf-8')
        (stage / 'release.json').unlink()
        release['gameRuntimeVerified'] = False
        release['pillarHeadlessCompatibility'] = profile
        release['modsInventory'] = validate_mods(stage)
        changed = {name for name, old in before.items() if release['modsInventory'].get(name) != old}
        require(changed == {CONFIG}, 'Existing files changed beyond Pillar config')
        require(inventory(base) == {**before, 'release.json': base_release_sha}, 'Base changed during assembly')
        (stage / 'release.json').write_text(json.dumps(release, indent=2), encoding='utf-8')
        require(not output.exists(), 'Output appeared during assembly')
        os.rename(stage, output)
    return {'output': str(output), 'assemblySha256': digest,
            'releaseSha256': sha256(output / 'release.json'), 'runtimeVerified': False, 'deployed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'build', 'config', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = assemble(args.base, args.build, args.config, args.output)
    except (OSError, ValueError, KeyError, configparser.Error) as error:
        parser.exit(1, 'Assembly failed: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
