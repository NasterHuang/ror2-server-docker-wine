"""Boot helper must not start unrelated containers or depend on timeout(1)."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


@unittest.skipIf(os.name == 'nt', 'Target router uses POSIX sh')
class RouterBootTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        docker = self.root / 'docker'
        docker.write_text('''#!/bin/sh
if [ "$1" = inspect ]; then
  case "$3" in
    *Labels*) echo "${FAKE_OWNER:-rains}";;
    *Health*) echo healthy;;
    *) echo "${FAKE_RUNNING:-true}";;
  esac
elif [ "$1" = start ]; then
  echo "$2" >> "$FAKE_MARKER"
  [ "${FAKE_HANG:-0}" = 0 ] || exec sleep 30
else exit 2
fi
''')
        docker.chmod(0o755)
        self.marker = self.root / 'starts'
        self.env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'], FAKE_MARKER=str(self.marker))
        self.script = Path(__file__).resolve().parents[1] / 'tools/immortalwrt-boot-start.sh'

    def run_helper(self, *args, **env):
        return subprocess.run(['sh', str(self.script), *args], env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=15)

    def test_running_container_is_untouched(self):
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.marker.exists())

    def test_other_project_is_rejected(self):
        result = self.run_helper(FAKE_OWNER='another-project')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_check_is_read_only_and_stopped_project_starts_once(self):
        self.assertEqual(self.run_helper('--check', FAKE_RUNNING='false').returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.run_helper(FAKE_RUNNING='false').returncode, 0)
        self.assertEqual(self.marker.read_text().splitlines(), ['rains-ror2-server-1'])

    def test_hung_docker_client_is_bounded_without_timeout_applet(self):
        start = time.monotonic()
        result = self.run_helper(FAKE_RUNNING='false', FAKE_HANG='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(time.monotonic() - start, 12)
