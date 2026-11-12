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

import csv
import json
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
from harborlens.ais import run
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
    read_memory_bound,
    require_multiday_schema,
    require_pinned_working_set,
    run_multiday,
    soft_heap_limit_enforced,
)
from harborlens.segmentation import MemoryStore, SegmentationParams, Segmenter

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais.csv"
GOLDEN = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev9"
PROBE = Path(__file__).resolve().parent / "multiday_memory_probe.py"
# Package 0.2.0.dev9 at 9a9e00bb932058c34184e63491ca01fa710a7253.
DEV9_RUN_ID = "c8f646f7b6fd49bf0fee224d9d65a92ee9345df26734c6fea753fbf47ad633ee"

HEADER = "MMSI,BaseDateTime,LAT,LON,SOG,VesselType,Status\n"
MMSI = "367110001"
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
ROWS_PER_DAY = 4 * (24 * 60 // 4)  # 4 vessels, one point every 4 minutes
DAY_COUNTS = (1, 3, 7, 14)


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
    for vessel_i, mmsi in enumerate(("367110001", "367110002", "367110003", "367110004")):
        lat = 29.50 + vessel_i * 0.01
        for minute in minutes:
            rows.append(line(start + timedelta(minutes=minute), mmsi=mmsi, lat=lat, lon=-95.20))
    return rows


def sqlite3_mutated(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("PRAGMA cache_size=-262144")
    db.execute("PRAGMA soft_heap_limit=0")
    db.execute("PRAGMA mmap_size=268435456")
    return db


def assert_enforced_pin(test, bound):
    """The bound that is always enforced: cache, mmap, and temp_store.

    ``soft_heap_limit_enforced`` is recorded and is not assumed to be true.
    """
    test.assertEqual(bound["policy"], MEMORY_BOUND_POLICY)
    test.assertEqual(bound["sqlite_cache_kib"], SQLITE_CACHE_KIB)
    test.assertEqual(bound["mmap_bytes"], 0)
    test.assertEqual(bound["temp_store"], "FILE")
    test.assertFalse(bound["grows_with_input_rows"])
    test.assertIn(bound["soft_heap_limit_enforced"], ("true", "false", "unknown"))
    if bound["soft_heap_limit_enforced"] == "true":
        test.assertEqual(bound["sqlite_soft_heap_bytes"], SQLITE_SOFT_HEAP_BYTES)


class SqliteMemoryBoundTests(unittest.TestCase):
    def test_pragmas_match_the_fixed_bound(self):
        self.assertEqual(SQLITE_CACHE_KIB, 8192)
        self.assertEqual(SQLITE_SOFT_HEAP_BYTES, 8 * 1024 * 1024)
        self.assertEqual(MEMORY_BOUND_POLICY, "fixed-sqlite-heap-v1")
        self.assertEqual(MULTIDAY_SCHEMA_VERSION, "multi-day-1.1")
        with tempfile.TemporaryDirectory() as folder:
            db = _make_db(Path(folder) / "bound.sqlite3", 32)
            try:
                record = read_memory_bound(db)
                require_pinned_working_set(record)
                assert_enforced_pin(self, record)
                self.assertEqual(soft_heap_limit_enforced(db), record["soft_heap_limit_enforced"])
                self.assertEqual(db.execute("PRAGMA cache_size").fetchone()[0], -SQLITE_CACHE_KIB)
                self.assertEqual(db.execute("PRAGMA mmap_size").fetchone()[0], 0)
                self.assertEqual(db.execute("PRAGMA temp_store").fetchone()[0], 1)
            finally:
                db.close()

    def test_refused_pragma_fails_closed(self):
        class Fake:
            def execute(self, sql):
                return self

            def fetchone(self):
                return (0,)

            def fetchall(self):
                return [("COMPILER=test",)]

        with self.assertRaisesRegex(AISInputError, "fixed multi-day pin"):
            _apply_memory_bound(Fake())

    def test_mutated_pin_is_rejected(self):
        """A 256 MiB cache, soft heap 0, mmap on, and temp_store=MEMORY is not the pin.

        The 14-day scaling fixture is about 4 MiB of scratch, and on a GitHub
        runner the RSS gap for a 400,000-row load was only about 6 MiB
        (pinned already near 100 MiB). RSS does not fail that mutation.
        The live read-back does: cache, mmap, and temp store must match the pin.
        """
        with tempfile.TemporaryDirectory() as folder:
            db = sqlite3_mutated(Path(folder) / "probe.sqlite3")
            try:
                mutated = read_memory_bound(db)
            finally:
                db.close()
            self.assertEqual(mutated["sqlite_cache_kib"], 262144)
            self.assertEqual(mutated["sqlite_soft_heap_bytes"], 0)
            self.assertEqual(mutated["mmap_bytes"], 268435456)
            self.assertEqual(mutated["temp_store"], "MEMORY")
            with self.assertRaisesRegex(AISInputError, "cache_kib=262144") as caught:
                require_pinned_working_set(mutated)
            self.assertIn("temp_store=MEMORY", str(caught.exception))
            self.assertIn("mmap_bytes=268435456", str(caught.exception))

    def test_pipeline_rejects_a_monkeypatched_pin(self):
        def bad(db):
            db.execute("PRAGMA temp_store=MEMORY")
            db.execute("PRAGMA cache_size=-262144")
            db.execute("PRAGMA soft_heap_limit=0")
            db.execute("PRAGMA mmap_size=268435456")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_csv(root / "a.csv", [line(DAY + timedelta(minutes=5 * i)) for i in range(4)])
            write_csv(root / "b.csv", [line(DAY + timedelta(days=1, minutes=5 * i)) for i in range(4)])
            with mock.patch("harborlens.multiday._apply_memory_bound", bad):
                with self.assertRaisesRegex(AISInputError, "fixed multi-day pin"):
                    run_multiday([root / "a.csv", root / "b.csv"], root / "out")
            self.assertFalse((root / "out" / "manifest.json").exists())

    def test_multiday_1_0_without_memory_bound_is_not_1_1(self):
        from jsonschema import Draft202012Validator

        legacy = {
            "schema_version": "multi-day-1.0",
            "resources": {
                "scratch_peak_bytes": 1,
                "scratch_measurement": "sampled at commits; includes rollback journal",
            },
        }
        snapshot = json.loads(json.dumps(legacy))
        with self.assertRaisesRegex(AISInputError, "not treated as 1.1"):
            require_multiday_schema(legacy)
        self.assertEqual(legacy, snapshot)
        self.assertNotIn("memory_bound", legacy["resources"])
        schema = json.loads((ROOT / "schemas" / "v1" / "multi-day-run.schema.json").read_text())
        errors = list(Draft202012Validator(schema).iter_errors(legacy))
        self.assertTrue(errors)
        self.assertTrue(any(err.validator == "const" for err in errors))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_csv(root / "a.csv", memory_day(0, range(0, 60, 4)))
            write_csv(root / "b.csv", memory_day(1, range(0, 60, 4)))
            manifest = run_multiday([root / "a.csv", root / "b.csv"], root / "out")
        self.assertEqual(manifest["schema_version"], "multi-day-1.1")
        self.assertIs(require_multiday_schema(manifest), manifest)
        Draft202012Validator(schema).validate(manifest)


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
            write_csv(path, [line(when, mmsi=f"36711{index:04d}")])
            paths.append(path)
        manifest = run_multiday(paths, self.root / "sixteen")
        self.assertEqual(manifest["counts"]["written"], MAX_FILES)
        self.assertEqual(len(manifest["input_files"]), MAX_FILES)
        self.assertEqual(manifest["schema_version"], "multi-day-1.1")
        assert_enforced_pin(self, manifest["resources"]["memory_bound"])
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
                assert_enforced_pin(self, payload["memory_bound"])
                manifest = json.loads((out / "manifest.json").read_text())
                self.assertEqual(manifest["schema_version"], MULTIDAY_SCHEMA_VERSION)
                assert_enforced_pin(self, manifest["resources"]["memory_bound"])
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
                    "soft_heap_limit_enforced": item["memory_bound"]["soft_heap_limit_enforced"],
                    "sqlite_cache_kib": item["memory_bound"]["sqlite_cache_kib"],
                    "temp_store": item["memory_bound"]["temp_store"],
                    "mmap_bytes": item["memory_bound"]["mmap_bytes"],
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
            # Keep the table in the failure output and in a successful assertion message
            # only when something is wrong. Print it for the PR measurement log.
            print("\nMULTIDAY_MEMORY_TABLE " + detail)


class MultiDayCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.a = write_csv(self.root / "a.csv", [line(DAY + timedelta(minutes=5 * i)) for i in range(4)])
        self.b = write_csv(self.root / "b.csv", [line(DAY + timedelta(days=1, minutes=5 * i)) for i in range(4)])

    def tearDown(self):
        self.tmp.cleanup()

    def _cli(self, args):
        return subprocess.run(
            [sys.executable, "-m", "harborlens.multiday", *args],
            check=False, capture_output=True, text=True,
        )

    def test_wrong_file_count_exits_2_without_traceback(self):
        for label, inputs in (
            ("one file", [self.a]),
            ("seventeen files", [self.a, self.b] + [
                write_csv(self.root / f"extra-{index}.csv", [line(DAY + timedelta(days=2 + index))])
                for index in range(15)
            ]),
        ):
            with self.subTest(label=label):
                proc = self._cli(["--input", *[str(path) for path in inputs], "--out", str(self.root / label)])
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertNotIn("Traceback", proc.stdout)
                self.assertIn("distinct AIS files", proc.stderr)
                self.assertEqual(proc.stdout, "")

    def test_existing_output_exits_2_without_traceback(self):
        out = self.root / "out"
        first = self._cli(["--input", str(self.a), str(self.b), "--out", str(out)])
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self._cli(["--input", str(self.a), str(self.b), "--out", str(out)])
        self.assertEqual(second.returncode, 2, second.stderr)
        self.assertNotIn("Traceback", second.stderr)
        self.assertNotIn("Traceback", second.stdout)
        self.assertIn("already exist", second.stderr)
        self.assertEqual(second.stdout, "")


class SingleDayByteIdentityTests(unittest.TestCase):
    """Cleaned CSV, candidate CSV and candidate GeoJSON match package 0.2.0.dev9.

    The manifest matches that package except ``input_file``, ``output``,
    ``run_id`` and ``code_version``. ``run_id`` changes only because it hashes
    ``harborlens_version``. ``git_commit`` is environment metadata.
    """

    def test_single_day_outputs_match_dev9_except_version_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = run(FIXTURE, root / "out")
            for name in ("houston_clean.csv", "stationary_candidates.csv",
                         "stationary_candidates.geojson"):
                self.assertEqual((root / "out" / name).read_bytes(), (GOLDEN / name).read_bytes(), name)
            golden = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(golden["run_id"], DEV9_RUN_ID)
            self.assertEqual(golden["code_version"]["package_version"], "0.2.0.dev9")
            self.assertEqual(_scrub(manifest), _scrub(golden))
            self.assertEqual(manifest["code_version"]["package_version"], harborlens.__version__)
            with mock.patch.object(provenance, "__version__", "0.2.0.dev9"):
                pinned = run(FIXTURE, root / "pinned")
            self.assertEqual(pinned["run_id"], DEV9_RUN_ID)
            self.assertEqual(pinned["code_version"]["package_version"], "0.2.0.dev9")
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
