"""Regression checks for a process interrupted between runtime rename operations."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "recovery_runtime", Path(__file__).parents[1] / "tools/runtime.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.previous = self.data / "previous"
        self.previous.mkdir(parents=True)
        (self.previous / "sentinel").write_bytes(b"last-working-release")
        self.current = self.data / "runtime"

    def assert_recovered(self):
        self.assertEqual((self.current / "sentinel").read_bytes(), b"last-working-release")
        self.assertFalse(self.previous.exists())

    def test_interrupted_promotion_restores_previous_and_is_idempotent(self):
        unfinished = self.data / "staging-interrupted"
        unfinished.mkdir()
        (unfinished / "partial").write_bytes(b"unvalidated")
        self.assertTrue(runtime.recover_interrupted_promotion(self.data))
        self.assert_recovered()
        self.assertFalse(runtime.recover_interrupted_promotion(self.data))
        self.assert_recovered()
        self.assertEqual((unfinished / "partial").read_bytes(), b"unvalidated")

    def test_completed_promotion_does_not_replace_current(self):
        self.current.mkdir()
        (self.current / "sentinel").write_bytes(b"new-release")
        self.assertFalse(runtime.recover_interrupted_promotion(self.data))
        self.assertEqual((self.current / "sentinel").read_bytes(), b"new-release")
        self.assertEqual((self.previous / "sentinel").read_bytes(), b"last-working-release")

    def test_missing_data_has_nothing_to_recover(self):
        absent = self.root / "not-created"
        self.assertFalse(runtime.recover_interrupted_promotion(absent))
        self.assertFalse(absent.exists())

    def prepare_fixture(self):
        source = self.root / "source"
        (source / runtime.MANAGED).parent.mkdir(parents=True)
        (source / runtime.MANAGED).write_bytes(b"clean-dll")
        (source / runtime.EXE).write_bytes(b"clean-exe")
        manifest = self.root / "patch-manifest.json"
        digest = runtime.sha256(source / runtime.MANAGED)
        manifest.write_text(json.dumps({"inputSha256": digest, "startup": [{}], "lobby": [{}]}))
        env = {"ACK_EXPERIMENTAL": "1", "EXPECTED_GAME_SHA256": digest,
               "PATCH_MANIFEST": str(manifest), "STEAMWORKS_DIR": str(self.root / "no-support"),
               "MODS_ENABLED": "0"}
        return source, env

    def test_failed_patching_after_recovery_preserves_last_release(self):
        source, env = self.prepare_fixture()
        with mock.patch.object(runtime.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "patcher")):
            with self.assertRaises(subprocess.CalledProcessError):
                runtime.prepare(source, self.data, self.root / "mods", env, "patcher")
        self.assert_recovered()
        self.assertEqual(list(self.data.glob("staging-*")), [])

    def test_failed_promotion_after_recovery_preserves_last_release(self):
        source, env = self.prepare_fixture()
        original_rename = Path.rename

        def fake_patch(command, **kwargs):
            Path(command[command.index("--output") + 1]).write_bytes(b"patched-dll")
            Path(command[command.index("--report") + 1]).write_text("{}")
            return subprocess.CompletedProcess(command, 0)

        def fail_promotion(path, destination):
            if path.name.startswith("staging-") and Path(destination) == self.current:
                raise OSError("simulated promotion failure")
            return original_rename(path, destination)

        with mock.patch.object(runtime.subprocess, "run", side_effect=fake_patch), \
                mock.patch.object(Path, "rename", fail_promotion):
            with self.assertRaisesRegex(OSError, "promotion failure"):
                runtime.prepare(source, self.data, self.root / "mods", env, "patcher")
        self.assert_recovered()
        self.assertEqual(list(self.data.glob("staging-*")), [])

    def test_promotion_rejects_current_and_previous_symlinks(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "sentinel").write_bytes(b"outside-release")
        probe = self.root / "symlink-probe"
        try:
            probe.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink creation privilege unavailable")
            raise
        probe.unlink()
        for name in ("runtime", "previous"):
            with self.subTest(path=name):
                data = self.root / ("symlink-" + name)
                data.mkdir()
                link = data / name
                link.symlink_to(outside, target_is_directory=True)
                try:
                    with self.assertRaisesRegex(ValueError, "real directories"):
                        runtime.recover_interrupted_promotion(data)
                    self.assertTrue(link.is_symlink())
                    self.assertEqual((outside / "sentinel").read_bytes(), b"outside-release")
                finally:
                    link.unlink()


if __name__ == "__main__":
    unittest.main()
