"""Profile checks bind native offsets to exact runtime bytes, not config comments."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('native_profile', Path(__file__).resolve().parents[1] / 'tools/native_profile.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'runtime'
        self.root.mkdir()
        for relative, data in (('UnityPlayer.dll', b'exact-native-engine'),
                               (native.FPTS, b'audited-local-fork'),
                               (native.MANAGED, b'exact-reviewed-game')):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.metadata = {
            'schema': 1,
            'requiredFiles': {p: self.digest(p) for p in ('UnityPlayer.dll', native.FPTS)},
            'acceptedRoR2Sha256': [self.digest(native.MANAGED)],
            'configPath': native.CONFIG,
            'configValues': {'Overrides': {'FunctionOffsetLookupType': 'PreferPdb'},
                             'Cache': {'LastDownloadedGUID': 'EXACTGUID1',
                                       'IsFileCreatedOffset': '554320'}},
        }
        config = self.root / native.CONFIG
        config.parent.mkdir(parents=True)
        config.write_text('[Overrides]\nFunctionOffsetLookupType=PreferPdb\n[Cache]\n'
                          'LastDownloadedGUID=EXACTGUID1\nIsFileCreatedOffset=554320\n', encoding='utf-8')
        self.save()

    def digest(self, relative):
        return hashlib.sha256((self.root / relative).read_bytes()).hexdigest()

    def save(self):
        (self.root / native.METADATA).write_text(json.dumps(self.metadata), encoding='utf-8')

    def test_bepinex_comment_and_whitespace_rewrite_is_accepted(self):
        (self.root / native.CONFIG).write_text(
            '# rewritten by BepInEx\n[Cache]\n\n## Type: String\nLastDownloadedGUID = EXACTGUID1\n'
            'IsFileCreatedOffset = 554320\n\n[Overrides]\nFunctionOffsetLookupType = PreferPdb\n', encoding='utf-8')
        self.assertEqual(native.validate_native_profile(self.root)['schema'], 1)

    def test_unity_drift_is_rejected_before_native_hooks(self):
        (self.root / 'UnityPlayer.dll').write_bytes(b'new-engine-same-filename')
        with self.assertRaisesRegex(ValueError, 'file SHA256 differs: UnityPlayer.dll'):
            native.validate_native_profile(self.root)

    def test_guid_offset_and_lookup_drift_are_rejected(self):
        original = (self.root / native.CONFIG).read_text(encoding='utf-8')
        for old, new in (('EXACTGUID1', 'OTHERGUID1'), ('554320', '554321'), ('PreferPdb', 'Manual')):
            with self.subTest(setting=old):
                (self.root / native.CONFIG).write_text(original.replace(old, new), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'config value differs'):
                    native.validate_native_profile(self.root)

    def test_game_assembly_drift_is_rejected(self):
        (self.root / native.MANAGED).write_bytes(b'other-build')
        with self.assertRaisesRegex(ValueError, 'RoR2.dll SHA256 is not accepted'):
            native.validate_native_profile(self.root)

    def test_incomplete_engine_or_fork_pin_is_rejected(self):
        for missing in ('UnityPlayer.dll', native.FPTS):
            with self.subTest(missing=missing):
                original = self.metadata['requiredFiles']
                self.metadata['requiredFiles'] = {p: h for p, h in original.items() if p != missing}
                self.save()
                with self.assertRaisesRegex(ValueError, 'must pin UnityPlayer.dll'):
                    native.validate_native_profile(self.root)
                self.metadata['requiredFiles'] = original

    def test_second_active_fpts_without_pin_is_rejected(self):
        duplicate = self.root / 'BepInEx/patchers/other/FixPluginTypesSerialization.dll'
        duplicate.parent.mkdir()
        duplicate.write_bytes(b'untracked-other-native-hooks')
        with self.assertRaisesRegex(ValueError, 'active FPTS DLL is not pinned'):
            native.validate_native_profile(self.root)

    def test_absolute_and_parent_paths_are_rejected(self):
        for relative in ('../UnityPlayer.dll', '/UnityPlayer.dll', 'C:/UnityPlayer.dll',
                         'C:UnityPlayer.dll', '..\\UnityPlayer.dll', '//host/share/file'):
            with self.subTest(path=relative):
                self.metadata['requiredFiles'] = {relative: '0' * 64}
                self.save()
                with self.assertRaisesRegex(ValueError, 'path'):
                    native.validate_native_profile(self.root)

    def test_symlink_escape_is_rejected(self):
        outside = self.root.parent / 'outside.dll'
        outside.write_bytes(b'exact-native-engine')
        link = self.root / 'alias.dll'
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest('Symlink privilege unavailable')
        self.metadata['requiredFiles'] = {'alias.dll': self.digest('UnityPlayer.dll')}
        self.save()
        with self.assertRaisesRegex(ValueError, 'outside runtime'):
            native.validate_native_profile(self.root)

    def test_fixed_config_path_can_follow_runtime_managed_persistent_link(self):
        config = self.root / native.CONFIG
        persistent = self.root.parent / 'persistent-config'
        persistent.mkdir()
        (persistent / config.name).write_bytes(config.read_bytes())
        config.unlink()
        config.parent.rmdir()
        try:
            config.parent.symlink_to(persistent, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink privilege unavailable')
        self.assertEqual(native.validate_native_profile(self.root)['schema'], 1)

    def test_absent_metadata_preserves_legacy_behavior(self):
        (self.root / native.METADATA).unlink()
        self.assertIsNone(native.validate_native_profile(self.root))

    def test_defaults_cannot_supply_missing_explicit_values(self):
        (self.root / native.CONFIG).write_text('[DEFAULT]\nIsFileCreatedOffset=554320\n'
                                              '[Cache]\nLastDownloadedGUID=EXACTGUID1\n'
                                              '[Overrides]\nFunctionOffsetLookupType=PreferPdb\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'DEFAULT'):
            native.validate_native_profile(self.root)


if __name__ == '__main__':
    unittest.main()
