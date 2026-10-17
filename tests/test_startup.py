"""Stalled startup and stale telemetry must not look ready."""
import datetime
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import test_runtime

runtime = test_runtime.runtime


class StartupTests(unittest.TestCase):
    def test_query_alone_is_insufficient_when_tools_are_requested(self):
        now = datetime.datetime(2026, 10, 17, tzinfo=datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as root, mock.patch.object(runtime, 'a2s_info', return_value={'map': 'lobby'}):
            state = {'queryPort': 27016, 'requireGameTelemetry': True}
            with self.assertRaises(OSError):
                runtime.readiness(root, state, now)
            folder = Path(root) / 'status'
            folder.mkdir()
            valid = {'sampleUtc': now.isoformat(), 'gameLoadFinished': True, 'serverActive': True, 'steamLoggedOn': False}
            for changes in ({'sampleUtc': (now - datetime.timedelta(seconds=31)).isoformat()},
                            {'sampleUtc': (now + datetime.timedelta(seconds=6)).isoformat()},
                            {'sampleUtc': '2026-10-17T00:00:00'}, {'sampleUtc': None},
                            {'gameLoadFinished': False}, {'serverActive': False}):
                with self.subTest(changes=changes):
                    (folder / 'game.json').write_text(json.dumps(dict(valid, **changes)))
                    with self.assertRaises(ValueError):
                        runtime.readiness(root, state, now)
            (folder / 'game.json').write_text(json.dumps(valid))
            result = runtime.readiness(root, state, now)
            self.assertTrue(result['gameTelemetryFresh'])
            self.assertFalse(result['steamLoggedOn'])
            self.assertFalse(result['multiplayerVerified'])
            state['requireGameTelemetry'] = False
            (folder / 'game.json').unlink()
            self.assertEqual(runtime.readiness(root, state)['query'], {'map': 'lobby'})

    def test_startup_deadline_terminates_owned_children_and_clears_state(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root)
            x = mock.Mock(pid=101)
            game = mock.Mock(pid=102)
            x.poll.return_value = game.poll.return_value = None
            with mock.patch.object(runtime.signal, 'signal'), \
                    mock.patch.object(runtime.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=10**12)), \
                    mock.patch.object(runtime.subprocess, 'Popen', side_effect=[x, game]), \
                    mock.patch.object(runtime.subprocess, 'run') as wineserver, \
                    mock.patch.object(runtime.os, 'killpg', create=True) as kill, \
                    mock.patch.object(runtime.time, 'monotonic', side_effect=[0, 31]), \
                    mock.patch.object(runtime.time, 'sleep'), \
                    mock.patch.object(runtime.Path, 'exists', return_value=True), \
                    mock.patch.object(runtime, 'readiness', side_effect=ValueError('not ready')):
                with self.assertRaisesRegex(RuntimeError, 'within 30s'):
                    runtime.supervise(data / 'runtime', data, {'STARTUP_TIMEOUT_SECONDS': '30'})
            self.assertFalse((data / 'state.json').exists())
            self.assertEqual([c.args[0] for c in kill.call_args_list], [102, 101])
            wineserver.assert_called_once()
            x.wait.assert_called_once_with(timeout=10)
            game.wait.assert_called_once_with(timeout=10)


if __name__ == '__main__':
    unittest.main()
