"""Synthetic scale benchmark for harborlens-multiday (issue #35).

Generates synthetic, fictional AIS files (no real vessels) and reports runtime,
peak RSS, SQLite scratch peak and output sizes. Results describe software
resource use on synthetic data only, never vessel activity.

    python tools/benchmark_multiday.py --rows-per-day 560000 --days 7 --workdir /tmp/hl-bench
"""
import argparse
import csv
import json
import random
import resource
import time
from datetime import datetime, timedelta
from pathlib import Path

from harborlens.multiday import MAX_POINTS, MAX_SCRATCH_MIB, run_multiday


def generate(workdir, rows_per_day, days, vessels=800, seed=1):
    rng = random.Random(seed)
    mmsis = [f"1990{n:05d}" for n in range(vessels)]
    per = max(2, rows_per_day // vessels)
    paths = []
    for d in range(days):
        day = datetime(2024, 1, 2) + timedelta(days=d)
        path = workdir / f"synthetic-day-{d + 1}.csv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"])
            for mmsi in mmsis:
                lat, lon, moving = 29.2 + rng.random() * 0.8, -95.6 + rng.random() * 1.3, False
                for i in range(per):
                    if rng.random() < 0.02:
                        moving = not moving
                    if moving:
                        lat, lon = lat + 0.0003, lon + 0.0003
                    when = day + timedelta(seconds=int(i * 86400 / per))
                    writer.writerow([mmsi, when.strftime("%Y-%m-%d %H:%M:%S"), round(lat, 6), round(lon, 6),
                                     8.0 if moving else 0.1, "70", "1"])
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Synthetic harborlens-multiday scale benchmark")
    parser.add_argument("--rows-per-day", type=int, default=560_000)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=False)
    paths = generate(args.workdir, args.rows_per_day, args.days)
    started = time.perf_counter()
    result = run_multiday(paths, args.workdir / "out", max_points=MAX_POINTS, max_scratch_mib=MAX_SCRATCH_MIB)
    rows = result["counts"]["total"]
    print(json.dumps({
        "synthetic": True, "rows": rows, "days": args.days,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "scratch_peak_mib": round(result["resources"]["scratch_peak_bytes"] / 1048576, 1),
        "scratch_bytes_per_row": round(result["resources"]["scratch_peak_bytes"] / rows, 1),
        "cleaned_csv_mib": round(result["artifacts"]["houston_clean.csv"]["size_bytes"] / 1048576, 1),
        "limits": result["limits"],
    }, indent=2))


if __name__ == "__main__":
    main()
