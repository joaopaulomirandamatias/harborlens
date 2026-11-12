"""Subprocess probe for the multi-day working set. Synthetic inputs only.

The parent test generates fictional AIS files and starts one process per day
count so peak RSS is not inherited from a previous run. This module is not a
test (unittest discovery matches ``test*.py``). It prints one JSON object.
"""
from __future__ import annotations

import json
import resource
import sys
import tracemalloc
from pathlib import Path

from harborlens.multiday import run_multiday


def rss_bytes():
    """Peak resident set for this process, in bytes.

    Linux reports ``ru_maxrss`` in kibibytes. macOS reports bytes.
    """
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(rss)
    return int(rss) * 1024


def main(argv):
    if len(argv) < 3:
        raise SystemExit("usage: multiday_memory_probe.py OUT CSV [CSV ...]")
    out = Path(argv[1])
    inputs = [Path(item) for item in argv[2:]]
    # Imports stay outside the trace so the peak is the run, not module load.
    tracemalloc.start()
    result = run_multiday(inputs, out)
    _current, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    payload = {
        "input_files": len(inputs),
        "rows": result["counts"]["total"],
        "written": result["counts"]["written"],
        "stationary_candidates": result["events"]["stationary_candidates"],
        "cross_day_candidates": result["events"]["cross_day_candidates"],
        "traced_peak_bytes": traced_peak,
        "rss_bytes": rss_bytes(),
        "scratch_peak_bytes": result["resources"]["scratch_peak_bytes"],
        "memory_bound": result["resources"]["memory_bound"],
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
