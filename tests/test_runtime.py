"""Runtime boundary and rollback checks; no Steam, Wine, Docker or live server required."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("runtime", Path(__file__).parents[1] / "tools/runtime.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class ConfigurationTests(unittest.TestCase):
    def test_ports_are_distinct_and_bounded(self):
        for env in ({"PORT": "27016"}, {"PORT": "0"}, {"PORT": "65536"},
                    {"STEAM_QUERY_PORT": "abc"}, {"PORT": " 27015"},
                    {"PORT": "27015;quit"}, {"STEAM_SERVER_PORT": "-1"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                runtime.configuration(env)
        cfg = runtime.configuration({"PORT": "28015", "STEAM_QUERY_PORT": "28016", "STEAM_SERVER_PORT": "28017"})
        self.assertIn("sv_port 28015;", cfg)
        self.assertIn("steam_server_query_port 28016;", cfg)
        self.assertIn("steam_server_steam_port 28017;", cfg)

    def test_console_injection_is_rejected_in_every_string_field(self):
        for field in ("SERVER_HOSTNAME", "SERVER_PASSWORD", "SERVER_CUSTOM_TAGS"):
            for payload in ('name";quit', "name;quit", "name\nhost 0", "name\rquit", "name\\quit", "name\x00", "name\tquit"):
                with self.subTest(field=field, payload=payload), self.assertRaises(ValueError):
                    runtime.configuration({field: payload})
        self.assertIn('sv_hostname "中文 server";', runtime.configuration({"SERVER_HOSTNAME": "中文 server"}))

    def test_managed_arguments_cannot_be_overridden(self):
        for arguments in (["-logFile", "evil.log"], ["-LOGFILE", "evil.log"],
                          ["-executeMethod", "Danger.Run"], ["-batchmode"], ["+quit"],
                          {"key": "value"}, [1], ["bad\x00arg"]):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                runtime.extra_args({"EXTRA_ARGS_JSON": json.dumps(arguments)})
        self.assertEqual(runtime.extra_args({"EXTRA_ARGS_JSON": '["-force-d3d11"]'}), ["-force-d3d11"])

    def test_player_count_and_gamemode_validation(self):
        for env in ({"MAX_PLAYERS": "0"}, {"MAX_PLAYERS": "17"}, {"GAMEMODE": "ClassicRun;quit"}, {"STEAM_HEARTBEAT": "2"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                runtime.configuration(env)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.data, self.mods = (self.root / name for name in ("source", "data", "mods"))
        (self.source / runtime.MANAGED).parent.mkdir(parents=True)
        (self.source / runtime.MANAGED).write_bytes(b"clean-game-dll")
        (self.source / runtime.EXE).write_bytes(b"clean-game-exe")
        self.previous_runtime = self.data / "runtime"
        self.previous_runtime.mkdir(parents=True)
        (self.previous_runtime / "sentinel").write_bytes(b"known-good-runtime")
        self.mods.mkdir()
        self.manifest = self.root / "patch-manifest.json"
        digest = runtime.sha256(self.source / runtime.MANAGED)
        self.manifest.write_text(json.dumps({"inputSha256": digest,
                                            "startup": [{}], "lobby": [{}], "appIds": [{}]}))
        self.env = {"ACK_EXPERIMENTAL": "1", "EXPECTED_GAME_SHA256": digest,
                    "PATCH_MANIFEST": str(self.manifest), "MODS_ENABLED": "0"}

    def fake_patch(self, command, **kwargs):
        Path(command[command.index("--output") + 1]).write_bytes(b"patched-dll")
        Path(command[command.index("--report") + 1]).write_text("{}")
        return subprocess.CompletedProcess(command, 0)

    def prepare(self):
        return runtime.prepare(self.source, self.data, self.mods, self.env, "fake-patcher")

    def assert_old_runtime(self):
        self.assertEqual((self.previous_runtime / "sentinel").read_bytes(), b"known-good-runtime")
        self.assertEqual(list(self.data.glob("staging-*")), [])

    def loader(self):
        for relative in ("winhttp.dll", "doorstop_config.ini", "BepInEx/core/BepInEx.Preloader.dll"):
            path = self.mods / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"loader-placeholder")

    def test_success_promotes_complete_runtime_and_keeps_previous(self):
        with mock.patch.object(runtime.subprocess, "run", side_effect=self.fake_patch):
            current = self.prepare()
        self.assertEqual((current / runtime.MANAGED).read_bytes(), b"patched-dll")
        self.assertEqual((self.data / "previous/sentinel").read_bytes(), b"known-good-runtime")
        release = json.loads((current / "release.json").read_text())
        self.assertFalse(release["gameRuntimeVerified"])
        self.assertEqual(release["sourceSha256"], self.env["EXPECTED_GAME_SHA256"])
        self.assertIn("host 1;", (current / "Risk of Rain 2_Data/Config/server_startup.cfg").read_text())
        self.assertEqual((self.source / runtime.MANAGED).read_bytes(), b"clean-game-dll")

    def test_patcher_failure_preserves_old_runtime_and_cleans_stage(self):
        with mock.patch.object(runtime.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "patcher")):
            with self.assertRaises(subprocess.CalledProcessError):
                self.prepare()
        self.assert_old_runtime()

    def test_overlapping_input_and_data_rejected_before_any_mutation(self):
        candidates = [self.source, self.source / 'data', self.root,
                      self.data / 'runtime', self.data / 'previous']
        for source_or_data in candidates:
            # Test both nesting directions, including an equal path. Recovery
            # must not run even when an input happens to be named previous.
            source, data = ((self.source, source_or_data) if source_or_data in
                            (self.source, self.source / 'data', self.root) else (source_or_data, self.data))
            with self.subTest(source=source, data=data), \
                    mock.patch.object(runtime, 'recover_interrupted_promotion') as recover, \
                    mock.patch.object(runtime.shutil, 'copytree') as copy:
                with self.assertRaisesRegex(ValueError, 'must not overlap'):
                    runtime.prepare(source, data, self.mods, self.env, 'fake-patcher')
                recover.assert_not_called()
                copy.assert_not_called()
        self.assert_old_runtime()
        self.assertEqual((self.source / runtime.MANAGED).read_bytes(), b'clean-game-dll')

    def test_mod_and_sdk_inputs_must_not_overlap_data(self):
        for field in ('mods', 'support'):
            for input_path in (self.data, self.data / 'input', self.root):
                env = dict(self.env)
                mods = self.mods
                if field == 'mods':
                    env['MODS_ENABLED'] = '1'
                    mods = input_path
                else:
                    env['STEAMWORKS_DIR'] = str(input_path)
                with self.subTest(field=field, input=input_path), \
                        mock.patch.object(runtime, 'recover_interrupted_promotion') as recover:
                    with self.assertRaisesRegex(ValueError, 'must not overlap'):
                        runtime.prepare(self.source, self.data, mods, env, 'fake-patcher')
                    recover.assert_not_called()
        self.assert_old_runtime()

    def test_cli_rejects_overlap_without_removing_source_state(self):
        state = self.source / 'state.json'
        state.write_bytes(b'original-source-file')
        with mock.patch.dict(runtime.os.environ, self.env, clear=True), \
                mock.patch.object(runtime.sys, 'argv', ['runtime.py', 'prepare', '--source', str(self.source),
                                                       '--data', str(self.source)]), \
                mock.patch('builtins.print'):
            self.assertEqual(runtime.main(), 1)
        self.assertEqual(state.read_bytes(), b'original-source-file')
        self.assertFalse((self.source / '.runtime.lock').exists())

    def test_failed_promotion_restores_old_runtime(self):
        original = Path.rename

        def fail_stage(path, target):
            if path.name.startswith("staging-") and Path(target).name == "runtime":
                raise OSError("simulated promotion failure")
            return original(path, target)

        with mock.patch.object(runtime.subprocess, "run", side_effect=self.fake_patch), mock.patch.object(Path, "rename", fail_stage):
            with self.assertRaisesRegex(OSError, "promotion failure"):
                self.prepare()
        self.assert_old_runtime()

    def test_game_update_drift_is_rejected_before_patcher(self):
        (self.source / runtime.MANAGED).write_bytes(b"steam-updated-game")
        with mock.patch.object(runtime.subprocess, "run") as patcher:
            with self.assertRaisesRegex(ValueError, "SHA256 changed"):
                self.prepare()
        patcher.assert_not_called()
        self.assert_old_runtime()

    def test_manifest_cannot_pin_a_different_game(self):
        value = json.loads(self.manifest.read_text())
        value["inputSha256"] = "0" * 64
        self.manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "same clean game SHA256"):
            self.prepare()
        self.assert_old_runtime()

    def test_source_update_during_copy_is_rejected(self):
        original = runtime.shutil.copytree

        def mutate_after_copy(source, destination, *args, **kwargs):
            result = original(source, destination, *args, **kwargs)
            if Path(source) == self.source:
                (self.source / runtime.MANAGED).write_bytes(b"updated-during-copy")
            return result

        with mock.patch.object(runtime.shutil, "copytree", side_effect=mutate_after_copy), mock.patch.object(runtime.subprocess, "run") as patcher:
            with self.assertRaisesRegex(ValueError, "Source changed"):
                self.prepare()
        patcher.assert_not_called()
        self.assert_old_runtime()

    def test_mod_staging_cannot_replace_game_core(self):
        self.loader()
        (self.mods / runtime.EXE).write_bytes(b"injected-game")
        with self.assertRaisesRegex(ValueError, "may not replace game files"):
            runtime.validate_mods(self.mods)

    def test_mod_tool_generated_lock_metadata_is_accepted(self):
        self.loader()
        (self.mods / "mods-lock.json").write_text('{"schema": 1, "packages": []}')
        self.assertIn("mods-lock.json", runtime.validate_mods(self.mods))

    def test_mod_source_new_file_during_copy_is_rejected(self):
        self.loader()
        self.env["MODS_ENABLED"] = "1"
        original = runtime.shutil.copytree

        def inject_during_copy(source, destination, *args, **kwargs):
            if Path(source) == self.mods:
                (self.mods / runtime.EXE).write_bytes(b"injected-after-inventory")
            return original(source, destination, *args, **kwargs)

        # Avoid dependence on Windows developer-mode symlink privileges if the
        # implementation incorrectly reaches config activation before rejecting.
        def fake_link(path, target, target_is_directory=False):
            path.mkdir()

        with mock.patch.object(runtime.subprocess, "run", side_effect=self.fake_patch), \
                mock.patch.object(runtime.shutil, "copytree", side_effect=inject_during_copy), \
                mock.patch.object(Path, "symlink_to", fake_link):
            with self.assertRaisesRegex(ValueError, "[Mm]od.*changed|[Mm]od.*replace|[Mm]od.*inventory"):
                self.prepare()
        self.assert_old_runtime()


class ReleaseTests(unittest.TestCase):
    fake_patch = PreparationTests.fake_patch
    prepare = PreparationTests.prepare

    def setUp(self):
        PreparationTests.setUp(self)
        with mock.patch.object(runtime.subprocess, "run", side_effect=self.fake_patch):
            self.current = self.prepare()

    def test_release_verifies_without_source_tree(self):
        runtime.shutil.rmtree(self.source)
        release = runtime.verify_release(self.current, self.env)
        self.assertEqual(release["sourceSha256"], self.env["EXPECTED_GAME_SHA256"])

    def test_release_rejects_assembly_manifest_and_original_file_drift(self):
        for relative in (runtime.MANAGED, Path("patch-manifest.json"), Path(runtime.EXE)):
            with self.subTest(relative=relative):
                target = self.current / relative
                original = target.read_bytes()
                try:
                    target.write_bytes(b"unexpected-update")
                    with self.assertRaises(ValueError):
                        runtime.verify_release(self.current, self.env)
                finally:
                    target.write_bytes(original)

    def test_release_allows_generated_server_configuration(self):
        (self.current / "Risk of Rain 2_Data/Config/server.cfg").write_text('sv_hostname "changed";\n')
        self.assertEqual(runtime.verify_release(self.current, self.env)["sourceSha256"], self.env["EXPECTED_GAME_SHA256"])

    def test_release_requires_explicit_ack_and_matching_source_pin(self):
        for changes in ({"ACK_EXPERIMENTAL": "0"}, {"SERVER_MODE": "certified"}, {"EXPECTED_GAME_SHA256": "1" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runtime.verify_release(self.current, dict(self.env, **changes))

    def test_release_inventory_cannot_escape_runtime(self):
        manifest = self.current / "release.json"
        release = json.loads(manifest.read_text())
        release["sourceInventory"]["../outside"] = "0" * 64
        manifest.write_text(json.dumps(release))
        with self.assertRaisesRegex(ValueError, "inventory path"):
            runtime.verify_release(self.current, self.env)

    def test_release_rejects_unlocked_new_plugin(self):
        plugin = self.current / "BepInEx/plugins/Unexpected.dll"
        plugin.parent.mkdir(parents=True)
        plugin.write_bytes(b"unlocked-new-code")
        with self.assertRaises(ValueError):
            runtime.verify_release(self.current, self.env)

    def invoke_launch(self, supervisor):
        lock = types.SimpleNamespace(flock=mock.Mock(), LOCK_EX=2, LOCK_NB=4)
        with mock.patch.dict(sys.modules, {"fcntl": lock}), \
                mock.patch.object(sys, "argv", ["runtime.py", "launch", "--data", str(self.data)]), \
                mock.patch.dict(runtime.os.environ, dict(self.env, SERVER_HOSTNAME="Router server"), clear=True), \
                mock.patch.object(runtime, "supervise", supervisor), \
                mock.patch.object(runtime, "prepare", side_effect=AssertionError("launch must not restage or patch")):
            return runtime.main()

    def test_launch_reuses_release_regenerates_config_and_supervises(self):
        (self.data / "state.json").write_text('{"pid": 999999}')
        supervisor = mock.Mock(return_value=0)
        with mock.patch("builtins.print"):
            self.assertEqual(self.invoke_launch(supervisor), 0)
        self.assertEqual(supervisor.call_args.args[:2], (self.current, str(self.data)))
        self.assertIn('sv_hostname "Router server";', (self.current / "Risk of Rain 2_Data/Config/server_startup.cfg").read_text())
        self.assertFalse((self.data / "state.json").exists())
        self.assertEqual((self.current / runtime.MANAGED).read_bytes(), b"patched-dll")

    def test_launch_refuses_drift_before_supervisor(self):
        (self.current / runtime.MANAGED).write_bytes(b"changed")
        supervisor = mock.Mock()
        with mock.patch("builtins.print"):
            self.assertEqual(self.invoke_launch(supervisor), 1)
        supervisor.assert_not_called()


def info_reply(fixed=None):
    if fixed is None:
        fixed = struct.pack("<HBBBccBB", 632360 % 65536, 2, 4, 0, b"d", b"l", 0, 1) + b"1.0.0\0"
    return b"\xff\xff\xff\xffI\x11Server\0Stage\0ror2\0Risk of Rain 2\0" + fixed


class A2STests(unittest.TestCase):
    def socket(self, replies):
        sock = mock.MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.side_effect = replies
        return sock

    def test_challenge_is_echoed_once_and_info_is_parsed(self):
        challenge = b"\x01\x02\xff\x04"
        sock = self.socket([b"\xff\xff\xff\xffA" + challenge, info_reply()])
        with mock.patch.object(runtime.socket, "socket", return_value=sock):
            result = runtime.a2s_info("127.0.0.1", 28016, timeout=0.25)
        self.assertEqual(result, {"name": "Server", "map": "Stage", "appId16": 632360 % 65536, "players": 2, "maxPlayers": 4})
        initial = b"\xff\xff\xff\xffTSource Engine Query\0"
        self.assertEqual(sock.send.call_args_list, [mock.call(initial), mock.call(initial + challenge)])
        sock.settimeout.assert_called_once_with(0.25)
        sock.connect.assert_called_once_with(("127.0.0.1", 28016))

    def test_repeated_challenges_are_bounded(self):
        challenge = b"\xff\xff\xff\xffA1234"
        sock = self.socket([challenge, challenge])
        with mock.patch.object(runtime.socket, "socket", return_value=sock), self.assertRaises(ValueError):
            runtime.a2s_info("127.0.0.1", 27016)
        self.assertEqual(sock.send.call_count, 2)

    def test_invalid_split_and_truncated_info_responses_fail(self):
        for response in (b"", b"\xfe\xff\xff\xff" + b"split-packet", b"\xff\xff\xff\xffI\x11", info_reply(b"\x00" * 6)):
            with self.subTest(response=response):
                sock = self.socket([response])
                with mock.patch.object(runtime.socket, "socket", return_value=sock), self.assertRaises(ValueError):
                    runtime.a2s_info("127.0.0.1", 27016)

    def test_info_missing_visibility_vac_and_version_is_not_healthy(self):
        sock = self.socket([info_reply(b"\x00" * 7)])
        with mock.patch.object(runtime.socket, "socket", return_value=sock), self.assertRaises(ValueError):
            runtime.a2s_info("127.0.0.1", 27016)


if __name__ == "__main__":
    unittest.main()
