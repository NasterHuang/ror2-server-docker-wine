#!/usr/bin/env python3
"""Record Linux cgroup/proc metrics as JSONL; does not infer game frame time or RTT."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import time


def text(path):
    try:
        return Path(path).read_text(encoding='utf-8').strip()
    except OSError:
        return None


def pairs(path):
    raw = text(path)
    return dict(line.split(maxsplit=1) for line in raw.splitlines() if ' ' in line) if raw else None


def sample(data):
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'hostLoadavg': text('/proc/loadavg'),
            'cpuStat': pairs('/sys/fs/cgroup/cpu.stat'),
            'cpuMax': text('/sys/fs/cgroup/cpu.max'),
            'memoryCurrentBytes': text('/sys/fs/cgroup/memory.current'),
            'memoryPeakBytes': text('/sys/fs/cgroup/memory.peak'),
            'memoryEvents': pairs('/sys/fs/cgroup/memory.events'),
            'cpuPressure': text('/sys/fs/cgroup/cpu.pressure'),
            'memoryPressure': text('/sys/fs/cgroup/memory.pressure'),
            'ioPressure': text('/sys/fs/cgroup/io.pressure'),
            'diskFreeBytes': shutil.disk_usage(data).free}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds', type=int, default=60)
    p.add_argument('--interval', type=float, default=2.0)
    p.add_argument('--data', default='/data')
    a = p.parse_args()
    if not 1 <= a.seconds <= 86400 or not 0.1 <= a.interval <= 60:
        p.error('seconds must be 1..86400; interval must be 0.1..60')
    deadline = time.monotonic() + a.seconds
    while True:
        print(json.dumps(sample(a.data)), flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(a.interval, remaining))
