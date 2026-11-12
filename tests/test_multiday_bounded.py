"""Bounded-memory multi-day segmentation (SPEC-002, FR-009, NFR-004, NFR-007, BR-005, BR-007, BR-008).

Synthetic fixtures only. MMSIs are fictional. No authentic AIS, no licensed
rows, and no label sheet. A stationary candidate is unvalidated: it is not a
berth, anchorage, wait, or port call.

The 1/3/7/14-day memory check runs each input size in a fresh subprocess
(``tests/multiday_memory_probe.py``) so peak RSS is that process's high-water
mark. One day is two half-day files because ``harborlens-multiday`` requires
two inputs; the row count still scales 1:3:7:14.
"""
from __future__ import annotations

import contextlib
import csv
import inspect
import io
import json
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import harborlens
import harborlens.provenance as provenance
from harborlens.ais import header_alias, run
from harborlens.censoring import WindowCensoring
from harborlens.io_safe import AISInputError
from harborlens.multiday import (
    MAX_FILES,
    MEMORY_BOUND_POLICY,
    MULTIDAY_SCHEMA_VERSION,
    SQLITE_CACHE_KIB,
    SQLITE_SOFT_HEAP_BYTES,
    _apply_memory_bound,
    _make_db,
    main,
    memory_bound_record,
    run_multiday,
    soft_heap_limit_enforced,
)
from harborlens.segmentation import MemoryStore, SegmentationParams, Segmenter

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais.csv"
GOLDEN = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev15"
PROBE = Path(__file__).resolve().parent / "multiday_memory_probe.py"

HEADER = "MMSI,BaseDateTime,LAT,LON,SOG,VesselType,Status\n"
MMSI = "199011001"
DAY = datetime(2024, 1, 2, tzinfo=timezone.utc)
# Fixed ceilings with margin over Python 3.12 measurements.
# Traced peak was about 8.2 MiB and grew by about 66 KiB from 1 to 14 days.
# RSS for a given start was flat or grew by under 5 MiB. The absolute RSS
# varied from about 22 MiB to about 90 MiB across process starts, so the
# absolute ceiling is loose. The growth ceiling is the scaling property.
# Scratch grew with rows.
TRACED_PEAK_CEILING = 16 * 1024 * 1024
TRACED_GROWTH_CEILING = 1 * 1024 * 1024
RSS_CEILING = 192 * 1024 * 1024
RSS_GROWTH_CEILING = 16 * 1024 * 1024
# The 14-day scratch file is about 4 MiB. Process RSS growth stays under
# 16 MiB even with mmap on, so RSS does not notice a removed pin. The
# resident mapping of that file is 0 while mmap is off and about 4 MiB when
# mmap is on. 1 MiB sits between those two.
MAPPED_RSS_CEILING = 1 * 1024 * 1024
ROWS_PER_DAY = 4 * (24 * 60 // 4)  # 4 vessels, one point every 4 minutes
DAY_COUNTS = (1, 3, 7, 14)


def live_soft_heap_enforced():
    db = sqlite3.connect(":memory:")
    try:
        return soft_heap_limit_enforced(db)
    finally:
        db.close()


def stamp(when):
    return when.strftime("%Y-%m-%d %H:%M:%S")


def line(when, mmsi=MMSI, lat=29.73, lon=-95.16, sog=0.1, vessel_type="70"):
    return f"{mmsi},{stamp(when)},{lat:.5f},{lon:.5f},{sog},{vessel_type},1\n"


def write_csv(path, rows):
    path.write_text(HEADER + "".join(rows))
    return path


def memory_day(day_index, minutes):
    """One synthetic day. Four fictional MMSIs stay low-speed at fixed points."""
    start = DAY + timedelta(days=day_index)
    rows = []
    for vessel_i, mmsi in enumerate(("199011001", "199011002", "199011003", "199011004")):
        lat = 29.50 + vessel_i * 0.01
        for minute in minutes:
            rows.append(line(start + timedelta(minutes=minute), mmsi=mmsi, lat=lat, lon=-95.20))
    return rows


class _CompileOptions:
    def __init__(self, rows=None, error=False):
        self.rows = rows
        self.error = error

    def execute(self, sql):
        if self.error:
            raise sqlite3.OperationalError("compile_options unavailable")
        if not sql.startswith("PRAGMA compile_options"):
            raise AssertionError(sql)
        return self

    def fetchall(self):
        return self.rows


class SqliteMemoryBoundTests(unittest.TestCase):
    def test_pragmas_match_the_fixed_bound(self):
        self.assertEqual(SQLITE_CACHE_KIB, 8192)
        self.assertEqual(SQLITE_SOFT_HEAP_BYTES, 8 * 1024 * 1024)
        self.assertEqual(MEMORY_BOUND_POLICY, "fixed-sqlite-heap-v1")
        self.assertEqual(MULTIDAY_SCHEMA_VERSION, "multi-day-1.1")
        with tempfile.TemporaryDirectory() as folder:
            db = _make_db(Path(folder) / "bound.sqlite3", 32)
            try:
                enforced = soft_heap_limit_enforced(db)
                record = memory_bound_record(enforced)
                self.assertFalse(record["grows_with_input_rows"])
                self.assertEqual(record["sqlite_cache_kib"], SQLITE_CACHE_KIB)
                self.assertEqual(record["mmap_bytes"], 0)
                self.assertEqual(record["temp_store"], "FILE")
                self.assertEqual(record["soft_heap_limit_enforced"], enforced)
                self.assertIn(enforced, (True, False, "unknown"))
                names = [row[0] for row in db.execute("PRAGMA compile_options")]
                if enforced is True:
                    self.assertIn("ENABLE_MEMORY_MANAGEMENT", names)
                    self.assertEqual(record["sqlite_soft_heap_bytes"], SQLITE_SOFT_HEAP_BYTES)
                elif enforced is False:
                    self.assertNotIn("ENABLE_MEMORY_MANAGEMENT", names)
                    self.assertTrue(names)
                self.assertEqual(db.execute("PRAGMA cache_size").fetchone()[0], -SQLITE_CACHE_KIB)
                self.assertEqual(db.execute("PRAGMA soft_heap_limit").fetchone()[0],
                                 SQLITE_SOFT_HEAP_BYTES)
                self.assertEqual(db.execute("PRAGMA mmap_size").fetchone()[0], 0)
                self.assertEqual(db.execute("PRAGMA temp_store").fetchone()[0], 1)
                print(
                    "\nSQLITE_COMPILE_OPTIONS "
                    + json.dumps({
                        "sqlite_version": sqlite3.sqlite_version,
                        "soft_heap_limit_enforced": enforced,
                        "enable_memory_management": "ENABLE_MEMORY_MANAGEMENT" in names,
                    })
                )
            finally:
                db.close()

    def test_soft_heap_enforcement_is_true_false_or_unknown(self):
        self.assertIs(soft_heap_limit_enforced(_CompileOptions([
            ("COMPILER=gcc",), ("ENABLE_MEMORY_MANAGEMENT",),
        ])), True)
        self.assertIs(soft_heap_limit_enforced(_CompileOptions([
            ("SQLITE_ENABLE_MEMORY_MANAGEMENT",),
        ])), True)
        self.assertIs(soft_heap_limit_enforced(_CompileOptions([
            ("COMPILER=gcc",), ("TEMP_STORE=1",),
        ])), False)
        self.assertEqual(soft_heap_limit_enforced(_CompileOptions([])), "unknown")
        self.assertEqual(soft_heap_limit_enforced(_CompileOptions(error=True)), "unknown")
        self.assertEqual(soft_heap_limit_enforced(_CompileOptions([(None,)])), "unknown")
        with self.assertRaises(AISInputError):
            memory_bound_record("yes")

    def test_refused_pragma_fails_closed(self):
        class Fake:
            def execute(self, sql):
                if sql.startswith("PRAGMA cache_size") and "=" not in sql:
                    return self
                return self

            def fetchone(self):
                return (0,)

        with self.assertRaisesRegex(AISInputError, "memory bound"):
            _apply_memory_bound(Fake())


class DayBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def events(self, folder):
        with (folder / "stationary_candidates.csv").open(newline="") as handle:
            return list(csv.DictReader(handle))

    def test_exact_gap_boundary_across_midnight(self):
        # 23:00–23:50 and 00:05–00:55 is a 15-minute gap: one candidate (BR-003).
        first = [line(DAY + timedelta(hours=23, minutes=5 * i)) for i in range(11)]
        second = [line(DAY + timedelta(days=1, minutes=5 + 5 * i)) for i in range(11)]
        write_csv(self.root / "day-1.csv", first)
        write_csv(self.root / "day-2.csv", second)
        joined = run_multiday([self.root / "day-2.csv", self.root / "day-1.csv"], self.root / "joined")
        self.assertEqual(joined["events"]["stationary_candidates"], 1)
        self.assertEqual(joined["events"]["gap_splits"], 0)
        self.assertEqual(joined["events"]["cross_day_candidates"], 1)
        event = self.events(self.root / "joined")[0]
        self.assertEqual(event["confidence_label"], "unvalidated")
        self.assertEqual(event["type"], "stationary_candidate")
        self.assertEqual(event["left_censoring"], "unknown")
        self.assertEqual(event["right_censoring"], "unknown")
        self.assertEqual(event["crosses_utc_date"], "True")
        self.assertEqual(joined["source_rights_status"], "review_required")
        self.assertTrue(all(item["rights_status"] == "review_required" for item in joined["input_files"]))

        # One extra minute opens the gap. Each side still meets the minimums, so two candidates.
        later = [line(DAY + timedelta(days=1, minutes=6 + 5 * i)) for i in range(11)]
        write_csv(self.root / "day-2b.csv", later)
        split = run_multiday([self.root / "day-1.csv", self.root / "day-2b.csv"], self.root / "split")
        self.assertGreaterEqual(split["events"]["gap_splits"], 1)
        self.assertEqual(split["events"]["stationary_candidates"], 2)
        self.assertEqual(split["events"]["cross_day_candidates"], 0)

    def test_shuffled_files_match_time_order(self):
        ordered = []
        for minute in range(0, 80, 5):
            ordered.append(line(DAY + timedelta(hours=23, minutes=minute)))
        midpoint = 8  # 23:00 through 23:35, then 23:40 onward crosses midnight
        write_csv(self.root / "sorted-a.csv", ordered[:midpoint])
        write_csv(self.root / "sorted-b.csv", ordered[midpoint:])
        rng = random.Random(20241112)
        shuffled_a = ordered[:midpoint].copy()
        shuffled_b = ordered[midpoint:].copy()
        rng.shuffle(shuffled_a)
        rng.shuffle(shuffled_b)
        write_csv(self.root / "shuffled-a.csv", shuffled_a)
        write_csv(self.root / "shuffled-b.csv", shuffled_b)
        left = run_multiday([self.root / "sorted-a.csv", self.root / "sorted-b.csv"], self.root / "sorted")
        right = run_multiday([self.root / "shuffled-b.csv", self.root / "shuffled-a.csv"], self.root / "shuffled")
        # Source file names and hashes differ, so lineage columns differ. The candidate itself does not.
        self.assertEqual(_candidate_identity(self.root / "sorted"), _candidate_identity(self.root / "shuffled"))
        self.assertEqual(left["events"]["stationary_candidates"], 1)
        self.assertEqual(right["events"]["cross_day_candidates"], 1)
        self.assertNotEqual(left["run_id"], right["run_id"])  # different source bytes

    def test_late_point_in_the_next_file_stays_in_one_candidate(self):
        times = [DAY + timedelta(hours=23, minutes=5 * i) for i in range(16)]
        early, late = times[:8], times[8:]
        # Drop the interior point at index 3 from the first file and append it to the second.
        moved = early[3]
        write_csv(self.root / "chrono-a.csv", [line(item) for item in early])
        write_csv(self.root / "chrono-b.csv", [line(item) for item in late])
        write_csv(self.root / "late-a.csv", [line(item) for item in early if item != moved])
        write_csv(self.root / "late-b.csv", [line(moved)] + [line(item) for item in late])
        chrono = run_multiday([self.root / "chrono-a.csv", self.root / "chrono-b.csv"], self.root / "chrono")
        delayed = run_multiday([self.root / "late-a.csv", self.root / "late-b.csv"], self.root / "late")
        self.assertEqual(chrono["events"]["stationary_candidates"], 1)
        self.assertEqual(delayed["events"]["gap_splits"], 0)
        self.assertEqual(
            [row["event_id"] for row in self.events(self.root / "chrono")],
            [row["event_id"] for row in self.events(self.root / "late")],
        )
        self.assertEqual(self.events(self.root / "late")[0]["point_count"], "16")

    def test_same_timestamp_different_position_splits_and_duplicate_does_not(self):
        base = [line(DAY + timedelta(minutes=5 * i)) for i in range(10)]
        conflict = line(DAY + timedelta(minutes=20), lat=29.90)
        write_csv(self.root / "tie-a.csv", base + [conflict])
        write_csv(self.root / "tie-b.csv", [line(DAY + timedelta(days=1, hours=12))])
        conflicted = run_multiday([self.root / "tie-a.csv", self.root / "tie-b.csv"], self.root / "tie")
        self.assertGreaterEqual(conflicted["events"]["timestamp_conflicts"], 1)
        cleaned = (self.root / "tie" / "houston_clean.csv").read_text().splitlines()
        # Header plus the ten low-speed points, the conflicting point, and the next-day point.
        self.assertEqual(len(cleaned), 13)

        write_csv(self.root / "dup-a.csv", base)
        next_day = [line(DAY + timedelta(days=1, minutes=5 * i)) for i in range(10)]
        write_csv(self.root / "dup-b.csv", [base[0], *next_day])
        duplicated = run_multiday([self.root / "dup-a.csv", self.root / "dup-b.csv"], self.root / "dup")
        self.assertEqual(duplicated["counts"]["duplicate"], 1)
        self.assertEqual(duplicated["counts"]["duplicate_across_files"], 1)
        self.assertEqual(duplicated["counts"]["written"], len(base) + 10)

    def test_segmenter_rejects_descending_time(self):
        engine = Segmenter(
            SegmentationParams(), MemoryStore(), lambda record, group: None,
            WindowCensoring(None, 15),
        )
        engine.feed(MMSI, DAY + timedelta(minutes=5), 29.73, -95.16, 0.1)
        with self.assertRaisesRegex(AISInputError, "not sorted by MMSI and time"):
            engine.feed(MMSI, DAY, 29.73, -95.16, 0.1)

    def test_sixteen_files_run_and_seventeen_fail_closed(self):
        paths = []
        for index in range(MAX_FILES):
            path = self.root / f"part-{index:02d}.csv"
            when = DAY + timedelta(days=index)
            write_csv(path, [line(when, mmsi=f"199011{index:03d}")])
            paths.append(path)
        manifest = run_multiday(paths, self.root / "sixteen")
        self.assertEqual(manifest["counts"]["written"], MAX_FILES)
        self.assertEqual(len(manifest["input_files"]), MAX_FILES)
        self.assertEqual(manifest["schema_version"], "multi-day-1.1")
        self.assertEqual(manifest["resources"]["memory_bound"], memory_bound_record(live_soft_heap_enforced()))
        extra = self.root / "part-extra.csv"
        write_csv(extra, [line(DAY + timedelta(days=MAX_FILES))])
        out = self.root / "seventeen"
        with self.assertRaisesRegex(AISInputError, f"2–{MAX_FILES} distinct AIS files"):
            run_multiday(paths + [extra], out)
        self.assertFalse(out.exists())


class WorkingSetScalingTests(unittest.TestCase):
    def test_peak_memory_does_not_grow_with_days(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            minutes = range(0, 24 * 60, 4)
            for day in range(14):
                write_csv(root / f"day-{day + 1:02d}.csv", memory_day(day, minutes))
            # Two halves of day 0. Together they are one day's rows.
            write_csv(root / "half-a.csv", memory_day(0, range(0, 12 * 60, 4)))
            write_csv(root / "half-b.csv", memory_day(0, range(12 * 60, 24 * 60, 4)))
            measured = []
            for days in DAY_COUNTS:
                if days == 1:
                    inputs = [root / "half-a.csv", root / "half-b.csv"]
                else:
                    inputs = [root / f"day-{index + 1:02d}.csv" for index in range(days)]
                out = root / f"out-{days}"
                proc = subprocess.run(
                    [sys.executable, str(PROBE), str(out), *[str(path) for path in inputs]],
                    check=False, capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                payload = json.loads(proc.stdout)
                payload["days"] = days
                measured.append(payload)
                self.assertEqual(payload["written"], ROWS_PER_DAY * days)
                self.assertEqual(payload["stationary_candidates"], 4)
                self.assertEqual(payload["cross_day_candidates"], 0 if days == 1 else 4)
                self.assertEqual(payload["schema_version"], "multi-day-1.1")
                self.assertEqual(payload["memory_bound"], memory_bound_record(live_soft_heap_enforced()))
                self.assertFalse(payload["memory_bound"]["grows_with_input_rows"])
                with (out / "stationary_candidates.csv").open(newline="") as handle:
                    candidates = list(csv.DictReader(handle))
                self.assertEqual(len(candidates), 4)
                for candidate in candidates:
                    self.assertEqual(candidate["confidence_label"], "unvalidated")
                    self.assertEqual(candidate["type"], "stationary_candidate")
                    self.assertNotIn("berth", candidate["type"])

            by_days = {item["days"]: item for item in measured}
            traced_growth = by_days[14]["traced_peak_bytes"] - by_days[1]["traced_peak_bytes"]
            rss_growth = by_days[14]["rss_bytes"] - by_days[1]["rss_bytes"]
            table = [
                {
                    "days": item["days"],
                    "rows": item["rows"],
                    "traced_peak_bytes": item["traced_peak_bytes"],
                    "rss_bytes": item["rss_bytes"],
                    "scratch_peak_bytes": item["scratch_peak_bytes"],
                    "scratch_file_bytes": item["scratch_file_bytes"],
                    "sqlite_mapped_rss_bytes": item["sqlite_mapped_rss_bytes"],
                }
                for item in measured
            ]
            detail = json.dumps(table)
            for item in measured:
                self.assertLessEqual(item["traced_peak_bytes"], TRACED_PEAK_CEILING, detail)
                self.assertLessEqual(item["rss_bytes"], RSS_CEILING, detail)
            self.assertLessEqual(traced_growth, TRACED_GROWTH_CEILING, detail)
            self.assertLessEqual(rss_growth, RSS_GROWTH_CEILING, detail)
            scratches = [by_days[days]["scratch_peak_bytes"] for days in DAY_COUNTS]
            self.assertEqual(scratches, sorted(scratches))
            self.assertLess(scratches[0], scratches[-1])
            # The 14-day scratch file is larger than the mapping ceiling. The
            # pin keeps that file out of the process. A removed pin maps it.
            self.assertGreater(by_days[14]["scratch_file_bytes"], MAPPED_RSS_CEILING)
            # Keep the table in the failure output and in a successful assertion message
            # only when something is wrong. Print it for the PR measurement log.
            print("\nMULTIDAY_MEMORY_TABLE " + detail)
            if not Path("/proc/self/smaps").is_file():
                self.skipTest(
                    "/proc/self/smaps is absent, so sqlite_mapped_rss_bytes cannot be "
                    "measured (for example on macOS). Linux CI still fails when smaps "
                    "exists and the probe returns None."
                )
            for item in measured:
                self.assertIsNotNone(
                    item["sqlite_mapped_rss_bytes"],
                    "smaps exists but the probe returned None: " + detail,
                )
                self.assertLessEqual(item["sqlite_mapped_rss_bytes"], MAPPED_RSS_CEILING, detail)

    def test_mutated_pin_maps_the_scratch_file(self):
        """256 MiB cache, soft heap 0, mmap on, and temp_store MEMORY fails the measurement.

        The scaling test asserts ``sqlite_mapped_rss_bytes`` <= 1 MiB. This
        runs the same 14-day synthetic fixture with that pin removed and
        requires the resident mapping to exceed the ceiling. RSS growth at
        this size stays inside 16 MiB, which is why RSS alone does not bite.
        Without ``/proc/self/smaps`` the mapping cannot be read, so the check
        skips. On Linux, a ``None`` probe result still fails.
        """
        if not Path("/proc/self/smaps").is_file():
            self.skipTest(
                "/proc/self/smaps is absent, so a removed mmap pin cannot be measured "
                "(for example on macOS). This check still runs on Linux."
            )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            minutes = range(0, 24 * 60, 4)
            inputs = []
            for day in range(14):
                path = root / f"day-{day + 1:02d}.csv"
                write_csv(path, memory_day(day, minutes))
                inputs.append(path)
            env = os.environ.copy()
            env["HARBORLENS_MULTIDAY_TEST_PIN"] = "mutated"
            proc = subprocess.run(
                [sys.executable, str(PROBE), str(root / "out"), *[str(path) for path in inputs]],
                check=False, capture_output=True, text=True, env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            detail = json.dumps({
                "sqlite_mapped_rss_bytes": payload["sqlite_mapped_rss_bytes"],
                "scratch_file_bytes": payload["scratch_file_bytes"],
                "rss_bytes": payload["rss_bytes"],
                "memory_bound": payload["memory_bound"],
            })
            print("\nMUTATED_PIN_MAPPING " + detail)
            self.assertGreater(payload["scratch_file_bytes"], MAPPED_RSS_CEILING, detail)
            self.assertIsNotNone(
                payload["sqlite_mapped_rss_bytes"],
                "smaps exists but the probe returned None: " + detail,
            )
            self.assertGreater(payload["sqlite_mapped_rss_bytes"], MAPPED_RSS_CEILING, detail)
            self.assertEqual(payload["written"], ROWS_PER_DAY * 14)


class MultidayCliErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _exit(self, args):
        stderr = io.StringIO()
        stdout = io.StringIO()
        argv = ["harborlens-multiday", *args]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                main()
        return caught.exception.code, stderr.getvalue(), stdout.getvalue()

    def test_one_file_and_seventeen_files_exit_2(self):
        only = self.root / "only.csv"
        write_csv(only, [line(DAY)])
        code, text, _out = self._exit(["--input", str(only), "--out", str(self.root / "one")])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", text)
        self.assertIn("distinct AIS files", text)
        self.assertFalse((self.root / "one").exists())

        paths = []
        for index in range(MAX_FILES + 1):
            path = self.root / f"part-{index:02d}.csv"
            write_csv(path, [line(DAY + timedelta(days=index), mmsi=f"199011{index:03d}")])
            paths.append(str(path))
        code, text, _out = self._exit(["--input", *paths, "--out", str(self.root / "seventeen")])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", text)
        self.assertIn("distinct AIS files", text)
        self.assertFalse((self.root / "seventeen").exists())

    def test_existing_output_exits_2_without_clobber(self):
        first = self.root / "day-a.csv"
        second = self.root / "day-b.csv"
        write_csv(first, [line(DAY + timedelta(minutes=5 * i)) for i in range(4)])
        write_csv(second, [line(DAY + timedelta(days=1, minutes=5 * i)) for i in range(4)])
        out = self.root / "out"
        stdout = io.StringIO()
        argv = ["harborlens-multiday", "--input", str(first), str(second), "--out", str(out)]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            main()
        before = {path.name: path.read_bytes() for path in out.iterdir()}
        self.assertIn("manifest.json", before)
        code, text, _again = self._exit(["--input", str(first), str(second), "--out", str(out)])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", text)
        self.assertIn("already exist", text)
        self.assertEqual({path.name: path.read_bytes() for path in out.iterdir()}, before)

    def test_unreadable_input_exits_2_without_traceback(self):
        first = self.root / "day-a.csv"
        second = self.root / "day-b.csv"
        write_csv(first, [line(DAY)])
        write_csv(second, [line(DAY + timedelta(days=1))])
        out = self.root / "blocked"
        real_open = Path.open

        def opening(self_path, mode="r", *args, **kwargs):
            if mode == "rb" and self_path.resolve() == first.resolve():
                raise PermissionError("denied")
            return real_open(self_path, mode, *args, **kwargs)

        stderr = io.StringIO()
        argv = ["harborlens-multiday", "--input", str(first), str(second), "--out", str(out)]
        with mock.patch.object(Path, "open", opening), mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        text = stderr.getvalue()
        self.assertNotIn("Traceback", text)
        self.assertIn("cannot be accessed", text)
        self.assertFalse(out.exists())

    def test_malformed_header_exits_2_without_traceback(self):
        bad = self.root / "bad.csv"
        good = self.root / "good.csv"
        bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
        write_csv(good, [line(DAY + timedelta(days=1))])
        out = self.root / "header"
        code, text, _out = self._exit(["--input", str(bad), str(good), "--out", str(out)])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", text)
        self.assertIn("Missing", text)
        self.assertFalse(out.exists())
        with self.assertRaises(AISInputError):
            header_alias(["foo", "bar"], "mmsi")
        main_source = inspect.getsource(main)
        self.assertNotIn("except ValueError", main_source)
        self.assertNotIn("except (ValueError", main_source)

    def test_row_cap_and_empty_file_leave_no_output_directory(self):
        first = self.root / "day-a.csv"
        second = self.root / "day-b.csv"
        write_csv(first, [line(DAY), line(DAY + timedelta(minutes=1))])
        write_csv(second, [line(DAY + timedelta(days=1))])
        capped = self.root / "capped"
        code, text, _out = self._exit([
            "--input", str(first), str(second), "--out", str(capped), "--max-points", "1",
        ])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", text)
        self.assertIn("exceed cap", text)
        self.assertFalse(capped.exists())

        empty = self.root / "empty.csv"
        empty.write_bytes(b"")
        blank = self.root / "blank-out"
        code, text, _out = self._exit(["--input", str(first), str(empty), "--out", str(blank)])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", text)
        self.assertIn("empty", text)
        self.assertFalse(blank.exists())

        header_only = self.root / "header-only.csv"
        header_only.write_text(HEADER, encoding="utf-8")
        observations = self.root / "no-rows"
        code, text, _out = self._exit(
            ["--input", str(first), str(header_only), "--out", str(observations)]
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", text)
        self.assertIn("no AIS observations", text)
        self.assertFalse(observations.exists())


class SingleDayByteIdentityTests(unittest.TestCase):
    """Cleaned CSV, candidate CSV and candidate GeoJSON match package 0.2.0.dev15.

    The manifest matches that package except ``input_file``, ``output`` and
    ``git_commit``. ``git_commit`` is environment metadata. ``run_id`` hashes
    ``harborlens_version`` and the fixture digest, so it is pinned to the
    committed golden.
    """

    def test_single_day_outputs_match_dev15_except_path_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = run(FIXTURE, root / "out")
            for name in ("houston_clean.csv", "stationary_candidates.csv",
                         "stationary_candidates.geojson"):
                self.assertEqual((root / "out" / name).read_bytes(), (GOLDEN / name).read_bytes(), name)
            golden = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(golden["code_version"]["package_version"], "0.2.0.dev15")
            self.assertEqual(_scrub(manifest), _scrub(golden))
            self.assertEqual(manifest["code_version"]["package_version"], harborlens.__version__)
            self.assertEqual(manifest["run_id"], golden["run_id"])
            with mock.patch.object(provenance, "__version__", "0.2.0.dev15"):
                pinned = run(FIXTURE, root / "pinned")
            self.assertEqual(pinned["run_id"], golden["run_id"])
            self.assertEqual(pinned["code_version"]["package_version"], "0.2.0.dev15")
            for name in ("houston_clean.csv", "stationary_candidates.csv",
                         "stationary_candidates.geojson"):
                self.assertEqual((root / "pinned" / name).read_bytes(), (GOLDEN / name).read_bytes(), name)


def _candidate_identity(folder):
    with (folder / "stationary_candidates.csv").open(newline="") as handle:
        return [
            (row["event_id"], row["point_count"], row["start_utc"], row["end_utc"],
             row["duration_min"], row["crosses_utc_date"], row["confidence_label"])
            for row in csv.DictReader(handle)
        ]


def _scrub(manifest):
    body = json.loads(json.dumps(manifest))
    body["input_file"] = "INPUT"
    body["output"] = "OUTPUT"
    body["run_id"] = "RUN"
    body["code_version"] = {"package_version": "VERSION", "git_commit": None}
    return body


if __name__ == "__main__":
    unittest.main()
