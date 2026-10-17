#!/usr/bin/env python3
"""Assemble the exact audited FPTS overlay; never edits an installed game."""
import argparse
import configparser
import json
from pathlib import Path
import shutil

from runtime import sha256, validate_mods

FPTS = 'BepInEx/patchers/RiskofThunder-FixPluginTypesSerialization/FixPluginTypesSerialization/FixPluginTypesSerialization.dll'
CONFIG = 'BepInEx/config/FixPluginTypesSerialization.cfg'
STOCK = 'ea955d050d4c5977451e109a82ba52134c388707100e71a6626fd0a2c4521949'
UNITY = 'fae6c04f23916263879196211ed241aee5f1f1b53ba4566bb99d4df8526cc105'
GAME = ['48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c',
        '73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07']


def assemble(base, build, config, output):
    base, build, config, output = map(Path, (base, build, config, output))
    if output.exists():
        raise ValueError('Output must be a new directory')
    report = json.loads((build / 'build.json').read_text(encoding='utf-8'))
    dll = build / 'FixPluginTypesSerialization.dll'
    if sha256(dll) != report['assemblySha256'] or not report.get('localPatchesSha256'):
        raise ValueError('Requires a hash-verified maintained source build')
    if sha256(base / FPTS) != STOCK:
        raise ValueError('Base must contain the pinned official Thunderstore 1.0.4 DLL')
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str
    cfg.read_string(config.read_text(encoding='utf-8-sig'))
    if cfg['Cache']['LastDownloadedGUID'] != 'EEDAE5B1946F4B92AD8D6B3BD79F6C551':
        raise ValueError('Config does not match audited Unity identity')
    shutil.copytree(base, output)
    stock = output / FPTS
    stock.rename(stock.with_name(stock.name + '.disabled'))
    shutil.copy2(dll, stock)
    shutil.copy2(config, output / CONFIG)
    provenance = stock.parent / 'rains-source-overlay'
    provenance.mkdir(exist_ok=True)
    for name in ('build.json', 'LICENSE', 'upstream-provenance.json'):
        shutil.copy2(build / name, provenance / name)
    metadata = {'schema': 1, 'acceptedRoR2Sha256': GAME,
                'requiredFiles': {'UnityPlayer.dll': UNITY, FPTS: sha256(dll)},
                'configPath': CONFIG,
                'configValues': {section: dict(cfg[section]) for section in cfg.sections()}}
    (output / 'BepInEx/patchers/Rains.NativeCompatibility.json').write_text(
        json.dumps(metadata, indent=2), encoding='utf-8')
    release_path = output / 'release.json'
    if release_path.exists():
        release = json.loads(release_path.read_text(encoding='utf-8'))
        release_path.unlink()
        release['modsInventory'] = validate_mods(output)
        release['localSourceOverlays'] = [{'package': 'RiskofThunder-FixPluginTypesSerialization-1.0.4',
            'upstreamPackageDllSha256': STOCK, 'runtimeDllSha256': sha256(dll),
            'sourceCommit': report['commit'], 'localPatchesSha256': report['localPatchesSha256'],
            'runtimeVerified': False}]
        release['gameRuntimeVerified'] = False
        release_path.write_text(json.dumps(release, indent=2), encoding='utf-8')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'build', 'config', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    assemble(args.base, args.build, args.config, args.output)
    print('Prepared local source overlay with explicit provenance; runtime remains unverified.')
