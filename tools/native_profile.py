#!/usr/bin/env python3
"""Validate an optional, exact-build native compatibility profile without mutation."""
import configparser
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

METADATA = 'BepInEx/patchers/Rains.NativeCompatibility.json'
MANAGED = 'Risk of Rain 2_Data/Managed/RoR2.dll'
CONFIG = 'BepInEx/config/FixPluginTypesSerialization.cfg'
FPTS = ('BepInEx/patchers/RiskofThunder-FixPluginTypesSerialization/'
        'FixPluginTypesSerialization/FixPluginTypesSerialization.dll')
SHA256 = re.compile(r'[0-9a-fA-F]{64}')


def _require(condition, message):
    if not condition:
        raise ValueError('Native compatibility profile: ' + message)


def _file(root, relative, confine=True):
    _require(isinstance(relative, str) and relative and '\\' not in relative,
             'expected a relative POSIX file path')
    path = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    _require(not path.is_absolute() and not windows.drive and not windows.is_absolute()
             and all(part not in ('', '.', '..') for part in relative.split('/')),
             'unsafe relative file path')
    resolved = (root / relative).resolve()
    _require(not confine or resolved.is_relative_to(root), 'file resolves outside runtime: ' + relative)
    _require(resolved.is_file(), 'required file missing: ' + relative)
    return resolved


def _digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _hash(value):
    _require(isinstance(value, str) and SHA256.fullmatch(value), 'invalid SHA256 value')
    return value.lower()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate metadata key')
        result[key] = value
    return result


def validate_native_profile(runtime):
    """Return validated metadata, or None for legacy trees without metadata.

    Config is checked by section/key/value because BepInEx rewrites comments.
    This checks recorded identity and configuration, not native ABI correctness.
    """
    root = Path(runtime).resolve()
    candidate = root / METADATA
    if not candidate.exists() and not candidate.is_symlink():
        return None
    try:
        metadata_path = _file(root, METADATA)
        _require(metadata_path.stat().st_size <= 1024 * 1024, 'metadata exceeds size limit')
        metadata = json.loads(metadata_path.read_text(encoding='utf-8-sig'),
                              object_pairs_hook=_unique_object)
        _require(isinstance(metadata, dict) and type(metadata.get('schema')) is int
                 and metadata['schema'] == 1, 'unsupported schema')
        required = metadata.get('requiredFiles')
        _require(isinstance(required, dict) and required, 'requiredFiles must be a nonempty mapping')
        for relative, expected in required.items():
            expected = _hash(expected)
            path = _file(root, relative)
            _require(_digest(path) == expected, 'file SHA256 differs: ' + relative)
        _require('UnityPlayer.dll' in required and FPTS in required,
                 'requiredFiles must pin UnityPlayer.dll and the active FPTS DLL')
        for active in (root / 'BepInEx/patchers').rglob('*'):
            if active.name.lower() == 'fixplugintypesserialization.dll':
                _require(active.relative_to(root).as_posix() in required,
                         'active FPTS DLL is not pinned in requiredFiles')
        accepted = metadata.get('acceptedRoR2Sha256')
        _require(isinstance(accepted, list) and accepted, 'acceptedRoR2Sha256 must be a nonempty list')
        accepted = {_hash(value) for value in accepted}
        _require(_digest(_file(root, MANAGED)) in accepted, 'RoR2.dll SHA256 is not accepted')
        _require(metadata.get('configPath') == CONFIG, 'unexpected FPTS configPath')
        # Runtime owns/validates its persistent config-directory symlink. Only
        # this fixed configuration path may follow it outside the game tree.
        config_path = _file(root, metadata['configPath'], confine=False)
        _require(config_path.stat().st_size <= 1024 * 1024, 'config exceeds size limit')
        values = metadata.get('configValues')
        _require(isinstance(values, dict) and values, 'configValues must be a nonempty mapping')
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str
        config.read_string(config_path.read_text(encoding='utf-8-sig'))
        _require(not config.defaults(), 'DEFAULT config values are not supported')
        for section, options in values.items():
            _require(isinstance(section, str) and section and isinstance(options, dict) and options,
                     'invalid configValues section')
            _require(config.has_section(section), 'config section missing: ' + section)
            for key, expected in options.items():
                _require(isinstance(key, str) and key and isinstance(expected, str),
                         'invalid configValues entry')
                _require(config.has_option(section, key) and config.get(section, key) == expected,
                         'config value differs: ' + section + '/' + key)
        return metadata
    except (OSError, UnicodeError, json.JSONDecodeError, configparser.Error) as exc:
        raise ValueError('Native compatibility profile: unreadable metadata/config or file') from exc
