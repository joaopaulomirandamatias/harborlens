"""Subprocess probe for the multi-day working set. Synthetic inputs only.

The parent test generates fictional AIS files and starts one process per day
count so peak RSS is not inherited from a previous run. This module is not a
test (unittest discovery matches ``test*.py``). It prints one JSON object.

``HARBORLENS_MULTIDAY_TEST_PIN=mutated`` replaces the production pin with a
256 MiB cache, soft heap 0, mmap on, and ``temp_store=MEMORY``. The parent
uses that only to show the resident-mapping measurement fails. It is not a
CLI flag and production runs never read it.
"""
from __future__ import annotations

import json
import os
import resource
import sys
import tracemalloc
from pathlib import Path

import harborlens.multiday as multiday
from harborlens.multiday import run_multiday


def rss_bytes():
    """Peak resident set for this process, in bytes.

    Linux reports ``ru_maxrss`` in kibibytes. macOS reports bytes.
    """
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(rss)
    return int(rss) * 1024


def sqlite_mapped_rss_bytes(db_path):
    """Resident bytes of mappings whose path is exactly the scratch database.

    ``mmap_size=0`` leaves this at 0. A positive mmap size makes a full scan
    resident in the process. ``None`` when ``/proc/self/smaps`` is absent.
    """
    smaps = Path("/proc/self/smaps")
    if not smaps.is_file():
        return None
    target = str(Path(db_path).resolve())
    total = 0
    current = False
    with smaps.open() as handle:
        for line in handle:
            if line and line[0] in "0123456789abcdef":
                parts = line.split(None, 5)
                current = len(parts) == 6 and parts[5].strip() == target
            elif current and line.startswith("Rss:"):
                total += int(line.split()[1]) * 1024
    return total


def _install_mutated_pin():
    """Apply the loose pin the measurement must reject. Test probe only."""

    def loose(db):
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("PRAGMA cache_size=-262144")
        db.execute("PRAGMA soft_heap_limit=0")
        db.execute("PRAGMA mmap_size=268435456")
        db.execute("PRAGMA shrink_memory")

    multiday._apply_memory_bound = loose


def main(argv):
    if len(argv) < 3:
        raise SystemExit("usage: multiday_memory_probe.py OUT CSV [CSV ...]")
    out = Path(argv[1])
    inputs = [Path(item) for item in argv[2:]]
    if os.environ.get("HARBORLENS_MULTIDAY_TEST_PIN") == "mutated":
        _install_mutated_pin()
    observed = {}
    original = multiday._write_outputs

    def wrapped(db, files, sources, params, export_cap_mib, censoring, meter):
        stats = original(db, files, sources, params, export_cap_mib, censoring, meter)
        # The connection is still open, so the scratch mapping is still resident.
        observed["sqlite_mapped_rss_bytes"] = sqlite_mapped_rss_bytes(meter.db_path)
        observed["scratch_file_bytes"] = meter.db_path.stat().st_size if meter.db_path.exists() else 0
        return stats

    multiday._write_outputs = wrapped
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
        "scratch_file_bytes": observed.get("scratch_file_bytes"),
        "sqlite_mapped_rss_bytes": observed.get("sqlite_mapped_rss_bytes"),
        "memory_bound": result["resources"]["memory_bound"],
        "schema_version": result["schema_version"],
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
