import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from snapshot import snapshot, ROOT_DIRS, ROOT_FILES


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game'
        self.game.mkdir()
        for name in ROOT_DIRS:
            (self.game / name).mkdir()
        for name in ROOT_FILES:
            (self.game / name).write_bytes(b'original')
        dll = self.game / 'Risk of Rain 2_Data/Managed/RoR2.dll'
        dll.parent.mkdir()
        dll.write_bytes(b'original-game')
        self.acf = self.root / 'appmanifest.acf'
        self.acf.write_text('"appid" "632360"\n"StateFlags" "4"\n"buildid" "123"\n"TargetBuildID" "123"')
        self.target = self.root / 'snapshot'

    def test_exports_only_game_files_and_no_steam_owner(self):
        (self.game / 'winhttp.dll').write_bytes(b'old-loader')
        (self.game / 'Mods').mkdir()
        (self.game / 'Mods/secret.txt').write_text('do-not-copy')
        result = snapshot(self.game, self.target, self.acf)
        self.assertEqual(result['buildId'], '123')
        self.assertFalse((self.target / 'winhttp.dll').exists())
        self.assertFalse((self.target / 'Mods').exists())
        self.assertTrue((self.game / 'winhttp.dll').exists())
        metadata = json.loads((self.target / 'game-source.json').read_text())
        self.assertFalse(metadata['steamFileIntegrityVerifiedByTool'])

    def test_pending_update_fails_without_partial_target(self):
        self.acf.write_text('"appid" "632360" "StateFlags" "4" "buildid" "123" "TargetBuildID" "456"')
        with self.assertRaisesRegex(ValueError, 'pending'):
            snapshot(self.game, self.target, self.acf)
        self.assertFalse(self.target.exists())

    def test_existing_target_is_never_overwritten(self):
        self.target.mkdir()
        marker = self.target / 'existing'
        marker.write_text('safe')
        with self.assertRaises(ValueError):
            snapshot(self.game, self.target, self.acf)
        self.assertEqual(marker.read_text(), 'safe')

    def test_old_backup_rejected_and_stage_cleaned(self):
        (self.game / 'Risk of Rain 2_Data/old.bak').write_text('patched-backup')
        with self.assertRaisesRegex(ValueError, 'Backups'):
            snapshot(self.game, self.target, self.acf)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('snapshot.staging-*')))


if __name__ == '__main__':
    unittest.main()
