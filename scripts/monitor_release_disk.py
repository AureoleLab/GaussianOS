"""Sample build-volume peak growth; stop with an explicit sibling .stop file."""
import json
import shutil
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
evidence = root / "build/public-beta/evidence"
stop = evidence / "disk-monitor.stop"
out = evidence / "disk-peak.json"
initial = {"I:/": 77560659968, "C:/": 108402282496}
minimum = dict(initial)
if out.exists():
    previous = json.loads(out.read_text(encoding="utf-8"))
    minimum = {volume: min(minimum[volume], previous["minimum_free_bytes"].get(volume, minimum[volume]))
               for volume in minimum}
prior = evidence / "../stage/assembly-disk-budget.json"
if prior.exists():
    minimum["I:/"] = min(minimum["I:/"], json.loads(prior.read_text())["minimum_free_bytes"])
samples = 0
while not stop.exists():
    free = {volume: shutil.disk_usage(volume).free for volume in initial}
    minimum = {volume: min(minimum[volume], free[volume]) for volume in initial}
    samples += 1
    report = {"timestamp": time.time(), "initial_free_bytes": initial,
              "minimum_free_bytes": minimum, "current_free_bytes": free,
              "observed_peak_growth_bytes": {volume: initial[volume] - minimum[volume] for volume in initial},
              "reserve_bytes": 15_000_000_000, "samples": samples,
              "scope": "Volume growth includes unrelated processes; pre-monitor peak includes assembly samples."}
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if free["I:/"] < 15_000_000_000:
        (evidence / "DISK-RESERVE-VIOLATED.txt").write_text(json.dumps(report, indent=2))
    time.sleep(5)
