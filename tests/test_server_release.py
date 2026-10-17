"""Server release boundaries; fake DLL bytes test packaging, not SDK authenticity."""
import json
from pathlib import Path
import types
import unittest
from unittest import mock

import test_runtime

runtime = test_runtime.runtime
SUPPORT_FILES = {"steamclient64.dll", "tier0_s64.dll", "vstdlib_s64.dll"}
GENERATED_FILES = ("Mods/enabled_mods.txt", "Risk of Rain 2_Data/StreamingAssets/ConVarNames.txt",
                   "config/config.vdf", "logs/connection_log_27015.txt")


class ServerReleaseTests(unittest.TestCase):
    def setUp(self):
        test_runtime.PreparationTests.setUp(self)
        self.support = self.root / "sdk-win64"
        self.env["STEAMWORKS_DIR"] = str(self.support)
        manifest = json.loads(self.manifest.read_text())
        manifest["serverBootstrap"] = {"enabled": True}
        self.manifest.write_text(json.dumps(manifest))

    def sdk_fixture(self, optional=False):
        self.support.mkdir(exist_ok=True)
        names = SUPPORT_FILES | ({"steamwebrtc64.dll"} if optional else set())
        for name in names:
            (self.support / name).write_bytes(("fixture-" + name).encode())
        return names

    def prepare(self, data=None):
        with mock.patch.object(runtime.subprocess, "run", side_effect=lambda *a, **kw:
                               test_runtime.PreparationTests.fake_patch(self, *a, **kw)):
            return runtime.prepare(self.source, data or self.data, self.mods, self.env, "fake-patcher")

    def test_prepare_copies_required_sdk_and_optional_webrtc(self):
        for optional in (False, True):
            with self.subTest(optional_webrtc=optional):
                names = self.sdk_fixture(optional)
                current = self.prepare(self.root / ("optional" if optional else "required"))
                release = runtime.verify_release(current, self.env)
                self.assertEqual(set(release["supportInventory"]), names)
                for name in names:
                    self.assertEqual((current / name).read_bytes(), (self.support / name).read_bytes())
                    self.assertEqual(release["supportInventory"][name], runtime.sha256(current / name))

    def test_bootstrap_without_sdk_is_rejected_before_patcher(self):
        for empty_exists in (False, True):
            with self.subTest(empty_directory=empty_exists):
                if empty_exists:
                    self.support.mkdir()
                with mock.patch.object(runtime.subprocess, "run") as patcher:
                    with self.assertRaisesRegex(ValueError, "requires genuine Windows Steamworks"):
                        runtime.prepare(self.source, self.data, self.mods, self.env, "fake-patcher")
                patcher.assert_not_called()
                self.assertEqual((self.previous_runtime / "sentinel").read_bytes(), b"known-good-runtime")

    def test_incomplete_sdk_and_unexpected_sdk_code_are_rejected(self):
        self.sdk_fixture()
        for missing in SUPPORT_FILES:
            with self.subTest(missing=missing):
                path = self.support / missing
                original = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaisesRegex(ValueError, "three Windows x64 DLLs"):
                        self.prepare()
                finally:
                    path.write_bytes(original)
        (self.support / "unexpected.dll").write_bytes(b"unlocked-code")
        with self.assertRaisesRegex(ValueError, "three Windows x64 DLLs"):
            self.prepare()

    def test_every_sdk_dll_is_verified_for_modification_and_deletion(self):
        names = self.sdk_fixture(optional=True)
        current = self.prepare()
        for name in names:
            path = current / name
            original = path.read_bytes()
            for mutation in ("modified", "missing"):
                with self.subTest(dll=name, mutation=mutation):
                    if mutation == "modified":
                        path.write_bytes(b"changed-code")
                    else:
                        path.unlink()
                    try:
                        with self.assertRaises((ValueError, OSError)):
                            runtime.verify_release(current, self.env)
                    finally:
                        path.write_bytes(original)
        runtime.verify_release(current, self.env)

    def test_new_generated_text_and_subsequent_drift_are_allowed(self):
        self.sdk_fixture()
        current = self.prepare()
        for relative in GENERATED_FILES:
            path = current / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("first generated text\n")
        runtime.verify_release(current, self.env)
        for relative in GENERATED_FILES:
            (current / relative).write_text("updated generated text\n")
        runtime.verify_release(current, self.env)

    def test_inventory_recorded_generated_text_may_also_drift(self):
        self.sdk_fixture()
        for relative in GENERATED_FILES:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("previous game-generated text\n")
        current = self.prepare()
        for relative in GENERATED_FILES:
            (current / relative).write_text("game regenerated text\n")
        runtime.verify_release(current, self.env)

    def test_generated_text_exceptions_do_not_allow_adjacent_dlls(self):
        self.sdk_fixture()
        current = self.prepare()
        for relative in ("Mods/unlocked.dll", "unlocked.dll", "ConVarNames.txt", "ConVarNames.txt.dll",
                         "Risk of Rain 2_Data/StreamingAssets/ConVarNames.txt.dll", "Mods/enabled_mods.txt.dll"):
            with self.subTest(relative=relative):
                path = current / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"unlocked-code")
                try:
                    with self.assertRaisesRegex(ValueError, "Unlocked new release file"):
                        runtime.verify_release(current, self.env)
                finally:
                    path.unlink()

    def test_low_disk_reserve_refuses_before_starting_wine_or_xvfb(self):
        (self.data / "state.json").write_text('{"pid": 1}')
        usage = types.SimpleNamespace(free=128 * 1024 * 1024 - 1)
        with mock.patch.object(runtime.signal, "signal"), \
                mock.patch.object(runtime.shutil, "disk_usage", return_value=usage), \
                mock.patch.object(runtime.subprocess, "Popen") as start, \
                mock.patch.object(runtime.subprocess, "run"):
            with self.assertRaisesRegex(RuntimeError, "Insufficient free disk"):
                runtime.supervise(self.previous_runtime, self.data, {"MIN_FREE_MB": "128"})
        start.assert_not_called()
        self.assertFalse((self.data / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
