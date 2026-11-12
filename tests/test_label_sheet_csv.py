"""Label-sheet formula neutralization (SPEC-003, FR-013, NFR-006, NFR-020, BR-001).

Synthetic vessel ids use MID 199. A stationary candidate is an unvalidated
low-speed interval. It is not a berth, anchorage, wait, or port call.

The sampling key is JSON. The label sheet is the only CSV the labeling path
writes. ``harborlens-label-agreement`` reads that sheet through ``_read_sheet``.
``harborlens-evaluate`` reads the adjudicated CSV through ``_read_labels``.
"""
import csv
import hashlib
import io
import contextlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from harborlens.ais import run
from harborlens.evaluation import ADJUDICATED_FIELDS, _read_labels, evaluate, main as evaluate_main
from harborlens.io_safe import AISInputError
from harborlens.labeling import (
    WARNING, _read_sheet, agreement, agreement_main, draw_sample, neutralize_text_cell, read_csv_cell,
    recover_text_cell, render_label_sheet, sample_main,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais.csv"
HEADER = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"]
DAY = datetime(2024, 1, 2)
# Sheet main writes for tests/fixtures/synthetic_ais.csv. The fixture has no
# formula trigger, so neutralization does not change a cell.
FIXTURE_SHEET = (
    "sample_id,mmsi,start_utc,end_utc,observed_points,centroid_lon,centroid_lat,"
    "vessel_type_mode,left_censoring,right_censoring,annotator_id,label,confidence,"
    "evidence_level,evidence_sources,fragment_of_longer_stop,duration_judgement,notes\n"
    "S0001,199080001,2024-01-02T00:00:00Z,2024-01-02T00:45:00Z,46,-95.159998,29.730001,"
    "70,unknown,unknown,,,,,,,,\n"
)
FIXTURE_SHEET_SHA256 = "d5430083cd4e580b6d88140e95e0196de8fff8f7f0e742c8c181cb790ded1803"
TRIGGERS = (
    ("equals", "=cmd"),
    ("plus", "+cmd"),
    ("minus", "-cmd"),
    ("at", "@cmd"),
    ("tab", "\tcmd"),
    ("carriage return", "\rcmd"),
    ("leading spaces", "  =cmd"),
    ("space then tab", " \t=cmd"),
    ("leading newline", "\n=cmd"),
    ("spaces then minus", "  -95"),
)


def base_row(sample_id="S0001", **overrides):
    row = {
        "sample_id": sample_id,
        "mmsi": "199010001",
        "start_utc": "2024-01-02T00:00:00Z",
        "end_utc": "2024-01-02T01:00:00Z",
        "observed_points": 8,
        "centroid_lon": -95.1,
        "centroid_lat": 29.7,
        "vessel_type_mode": "70",
        "left_censoring": "unknown",
        "right_censoring": "not_censored",
        "annotator_id": "A1",
        "label": "unknown",
        "confidence": "low",
        "evidence_level": "L2",
        "evidence_sources": "ais_track",
        "fragment_of_longer_stop": "unknown",
        "duration_judgement": "not_assessable",
        "notes": "",
    }
    row.update(overrides)
    return row


def trigger_row(index, text, annotator):
    sources = text if text.strip() else "ais_track"
    return base_row(
        sample_id=f"S{index:04d}",
        vessel_type_mode=text,
        annotator_id=annotator,
        evidence_sources=sources,
        notes=text,
        centroid_lon=-95.1,
        centroid_lat=29.7,
    )


def write_rendered(path, rows):
    path.write_bytes(render_label_sheet(rows).encode("utf-8"))
    return path


def track(mmsi, vessel_type, index):
    """One synthetic stop inside the Houston research box. Longitude stays negative."""
    out = []
    moment = DAY + timedelta(minutes=10 + index * 3)
    lat, lon = 29.4 + index * 0.02, -95.1
    for step in range(0, 45, 3):
        lon += 0.002
        out.append([mmsi, (moment + timedelta(minutes=step)).strftime("%Y-%m-%d %H:%M:%S"),
                    lat, lon, 8.0, vessel_type, "0"])
    moment += timedelta(minutes=45)
    for step in range(0, 41, 5):
        out.append([mmsi, (moment + timedelta(minutes=step)).strftime("%Y-%m-%d %H:%M:%S"),
                    lat, lon, 0.1, vessel_type, "1"])
    return out


class NeutralizerTests(unittest.TestCase):
    def test_each_trigger_and_leading_whitespace_round_trips_through_the_readers(self):
        """Logical text is recovered. A leading apostrophe on a number is not a number."""
        rows = [trigger_row(index, text, "A1") for index, (_, text) in enumerate(TRIGGERS, 1)]
        # annotator_id is itself a trigger on this copy, so that column is neutralized too.
        triggered_annotator = [trigger_row(1, "=cmd", "=A")]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sheet = write_rendered(root / "sheet.csv", rows)
            with sheet.open(newline="", encoding="utf-8") as handle:
                raw = list(csv.DictReader(handle))
            _annotator, labels = _read_sheet(sheet)
            self.assertEqual(_annotator, "A1")
            for (name, text), raw_row in zip(TRIGGERS, raw):
                with self.subTest(trigger=name):
                    self.assertTrue(raw_row["vessel_type_mode"].startswith("'"), raw_row["vessel_type_mode"])
                    self.assertTrue(raw_row["notes"].startswith("'"))
                    self.assertEqual(raw_row["centroid_lon"], "-95.1")
                    self.assertFalse(raw_row["centroid_lon"].startswith("'"))
                    self.assertEqual(raw_row["centroid_lat"], "29.7")
                    self.assertEqual(raw_row["mmsi"], "199010001")
                    self.assertEqual(raw_row["observed_points"], "8")
                    sid = raw_row["sample_id"]
                    self.assertEqual(labels[sid]["vessel_type_mode"], text)
                    self.assertEqual(labels[sid]["notes"], text)
                    if text.strip():
                        self.assertTrue(raw_row["evidence_sources"].startswith("'"))
                        self.assertEqual(labels[sid]["evidence_sources"], text)
                    self.assertEqual(labels[sid]["centroid_lon"], "-95.1")
                    if text.startswith("\r"):
                        self.assertIn(b'"\'\rcmd"', sheet.read_bytes())
            second = [trigger_row(index, text, "A2") for index, (_, text) in enumerate(TRIGGERS, 1)]
            write_rendered(root / "second.csv", second)
            report = agreement(sheet, root / "second.csv", root / "agreement.json")
            self.assertEqual(report["units"], len(TRIGGERS))
            self.assertFalse((root / "agreement.json.partial").exists())
            annotator_sheet = write_rendered(root / "annotator.csv", triggered_annotator)
            who, recovered = _read_sheet(annotator_sheet)
            self.assertEqual(who, "=A")
            self.assertEqual(recovered["S0001"]["notes"], "=cmd")

    def test_apostrophe_that_is_not_a_prefix_is_kept(self):
        """'=cmd on disk is the neutralized form of =cmd. 'hello is not a trigger."""
        self.assertEqual(recover_text_cell("'hello"), "'hello")
        self.assertEqual(recover_text_cell("'=cmd"), "=cmd")
        self.assertEqual(neutralize_text_cell("hello"), "hello")
        self.assertEqual(neutralize_text_cell("=cmd"), "'=cmd")
        self.assertEqual(neutralize_text_cell("J1"), "J1")
        # A raw value that already starts with an apostrophe is not the same cell.
        # The writer adds one more apostrophe. The reader removes exactly one.
        self.assertEqual(neutralize_text_cell("'=cmd"), "''=cmd")
        self.assertEqual(recover_text_cell("''=cmd"), "'=cmd")

    def test_apostrophe_rule_fullwidth_and_invisible_prefixes_round_trip(self):
        """Writer and reader are the real sheet path. Dropping a trigger fails a case."""
        cases = (
            ("plain apostrophe", "'abc", "'abc"),
            ("apostrophe then trigger", "'=x", "''=x"),
            ("two apostrophes then trigger", "''=x", "'''=x"),
            ("equals", "=x", "'=x"),
            ("bom then equals", "\ufeff=1+1", "'\ufeff=1+1"),
            ("zwsp then at", "\u200b@SUM", "'\u200b@SUM"),
            ("fullwidth equals", "\uff1dcmd", "'\uff1dcmd"),
            ("fullwidth plus", "\uff0bcmd", "'\uff0bcmd"),
            ("fullwidth minus", "\uff0dcmd", "'\uff0dcmd"),
            ("fullwidth at", "\uff20cmd", "'\uff20cmd"),
            ("nbsp then plus", "\u00a0+1", "'\u00a0+1"),
        )
        rows = [
            trigger_row(index, text, "A1")
            for index, (_, text, _disk) in enumerate(cases, 1)
        ]
        with tempfile.TemporaryDirectory() as folder:
            sheet = write_rendered(Path(folder) / "sheet.csv", rows)
            with sheet.open(newline="", encoding="utf-8") as handle:
                raw = list(csv.DictReader(handle))
            _who, labels = _read_sheet(sheet)
            self.assertEqual(_who, "A1")
            for (name, text, disk), raw_row in zip(cases, raw):
                with self.subTest(trigger=name):
                    self.assertEqual(raw_row["notes"], disk)
                    self.assertEqual(raw_row["vessel_type_mode"], disk)
                    sid = raw_row["sample_id"]
                    self.assertEqual(labels[sid]["notes"], text)
                    self.assertEqual(labels[sid]["vessel_type_mode"], text)
                    self.assertEqual(raw_row["centroid_lon"], "-95.1")
                    self.assertFalse(raw_row["centroid_lon"].startswith("'"))

    def test_excel_stripped_contract_cell_is_refused_with_exit_2_and_no_output(self):
        """A contract cell that returns as a formula, with no apostrophe, is refused."""
        stripped = (
            ("centroid_lon", "=1+1"),
            ("centroid_lat", "\uff1d29.7"),
            ("mmsi", "@199010001"),
            ("sample_id", "\ufeff=S0001"),
            ("label", "=SUM(A1)"),
            ("start_utc", "\t2024-01-02T00:00:00Z"),
        )
        for field, raw in stripped:
            with self.subTest(field=field):
                with self.assertRaises(AISInputError) as caught:
                    read_csv_cell(field, raw)
                message = str(caught.exception)
                self.assertIn("formula trigger", message)
                self.assertIn("not converted", message)
                self.assertIn(field, message)
        # A signed coordinate is a trigger character and a valid contract.
        self.assertEqual(read_csv_cell("centroid_lon", "-95.1"), "-95.1")
        self.assertEqual(read_csv_cell("centroid_lat", "+29.7"), "+29.7")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = write_rendered(root / "a.csv", [base_row(annotator_id="A1")])
            second = write_rendered(root / "b.csv", [base_row(annotator_id="A2")])
            text = first.read_text(encoding="utf-8").replace(",-95.1,29.7,", ",=1+1,29.7,", 1)
            tampered = root / "tampered.csv"
            tampered.write_text(text, encoding="utf-8")
            out = root / "agreement.json"
            stderr = io.StringIO()
            argv = ["harborlens-label-agreement", "--sheets", str(tampered), str(second),
                    "--out", str(out)]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    agreement_main()
            self.assertEqual(caught.exception.code, 2)
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertIn("formula trigger", stderr.getvalue())
            self.assertIn("centroid_lon", stderr.getvalue())
            self.assertFalse(out.exists())
            self.assertFalse(out.with_name(out.name + ".partial").exists())

    def test_negative_and_positive_coordinates_are_not_prefixed(self):
        text = render_label_sheet([
            base_row(sample_id="S0001", centroid_lon=-95.1, centroid_lat=29.7),
            base_row(sample_id="S0002", centroid_lon="-95.10", centroid_lat="+29.7"),
            base_row(sample_id="S0003", centroid_lon="+95.1", centroid_lat=29.7,
                     vessel_type_mode="-70"),
        ])
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(rows[0]["centroid_lon"], "-95.1")
        self.assertEqual(rows[1]["centroid_lon"], "-95.10")
        self.assertEqual(rows[1]["centroid_lat"], "+29.7")
        self.assertEqual(rows[2]["centroid_lon"], "+95.1")
        self.assertNotIn("'-95.1", text)
        self.assertNotIn("'+95.1", text)
        self.assertNotIn("'+29.7", text)
        # vessel_type_mode is text, so a leading minus is a formula trigger.
        self.assertEqual(rows[2]["vessel_type_mode"], "'-70")

    def test_contract_cells_with_a_leading_apostrophe_are_rejected(self):
        cases = {
            "centroid_lon": "'-95.1",
            "centroid_lat": "'29.7",
            "mmsi": "'199010001",
            "observed_points": "'8",
            "start_utc": "'2024-01-02T00:00:00Z",
            "label": "'unknown",
            "sample_id": "'S0001",
        }
        for field, raw in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(AISInputError) as caught:
                    read_csv_cell(field, raw)
                message = str(caught.exception)
                self.assertIn(raw, message)
                self.assertIn("not converted", message)
                self.assertNotEqual(message, raw[1:])

    def test_reader_rejects_a_prefixed_number_on_the_sheet_and_on_the_adjudicated_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sheet = write_rendered(root / "sheet.csv", [base_row()])
            with sheet.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["centroid_lon"] = "'-95.1"
            tampered = root / "tampered.csv"
            with tampered.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(AISInputError) as caught:
                _read_sheet(tampered)
            self.assertIn("'-95.1", str(caught.exception))
            self.assertIn("not converted", str(caught.exception))
            self.assertIn("centroid_lon", str(caught.exception))

            labels = root / "labels.csv"
            with labels.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=ADJUDICATED_FIELDS, lineterminator="\n")
                writer.writeheader()
                writer.writerow({
                    "sample_id": "S0001",
                    "label": "'unknown",
                    "evidence_level": "L2",
                    "duration_judgement": "assessable",
                    "true_start_utc": "'2024-01-02T00:00:00Z",
                    "true_end_utc": "'2024-01-02T01:00:00Z",
                    "adjudicator_id": neutralize_text_cell("=J1"),
                })
            with self.assertRaises(AISInputError) as caught:
                _read_labels(labels, {"S0001"})
            message = str(caught.exception)
            self.assertIn("not converted", message)
            self.assertIn("'unknown", message)
            self.assertIn("'2024-01-02T00:00:00Z", message)
            # The text column would have been recovered. The contract failure rejects the row.
            self.assertIn("'=J1", labels.read_text(encoding="utf-8"))

    def test_adjudicated_reader_recovers_only_the_text_column(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            run(FIXTURE, run_dir)
            draw_sample(run_dir, root / "sheet.csv", 3, candidates=5, negatives=0)
            plan = json.loads((root / "sheet.csv.sampling.json").read_text(encoding="utf-8"))
            labels = root / "adjudicated.csv"
            with labels.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=ADJUDICATED_FIELDS, lineterminator="\n")
                writer.writeheader()
                for unit in plan["key"]:
                    writer.writerow({
                        "sample_id": unit["sample_id"],
                        "label": "unknown",
                        "evidence_level": "L2",
                        "duration_judgement": "not_assessable",
                        "true_start_utc": "",
                        "true_end_utc": "",
                        "adjudicator_id": neutralize_text_cell("=J1"),
                    })
            loaded = _read_labels(labels, {unit["sample_id"] for unit in plan["key"]})
            self.assertTrue(loaded)
            for row in loaded.values():
                self.assertEqual(row["adjudicator_id"], "=J1")
                self.assertEqual(row["label"], "unknown")
            out = root / "eval.json"
            report = evaluate(run_dir, root / "sheet.csv.sampling.json", labels, out)
            self.assertEqual(report["validation_status"], "unvalidated")
            self.assertTrue(out.is_file())
            self.assertFalse(out.with_name(out.name + ".partial").exists())

    def test_invalid_contract_cells_raise_and_the_cli_writes_nothing(self):
        rejected = {
            "centroid_lon": "not-a-number",
            "centroid_lat": " -95.1",
            "mmsi": "=199010001",
            "observed_points": "-1",
            "start_utc": "2024-01-02 00:00:00",
            "left_censoring": "=unknown",
            "sample_id": "=S0001",
        }
        for field, value in rejected.items():
            with self.subTest(field=field):
                with self.assertRaises(AISInputError) as caught:
                    render_label_sheet([base_row(**{field: value})])
                self.assertIn(field, str(caught.exception))

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            run(FIXTURE, run_dir)
            sheet = root / "nested" / "bad.csv"
            real_load = __import__("harborlens.labeling", fromlist=["_load_run"])._load_run

            def corrupt(path):
                loaded = real_load(path)
                loaded[3][0]["lon"] = "not-a-number"
                return loaded

            stderr = io.StringIO()
            argv = ["harborlens-label-sample", "--run", str(run_dir), "--sheet", str(sheet),
                    "--seed", "1", "--candidates", "5", "--negatives", "0"]
            with mock.patch("harborlens.labeling._load_run", corrupt), mock.patch.object(sys, "argv", argv), \
                    contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    sample_main()
            self.assertEqual(caught.exception.code, 2)
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertIn("centroid_lon", stderr.getvalue())
            self.assertFalse(sheet.exists())
            self.assertFalse(sheet.with_name(sheet.name + ".partial").exists())
            self.assertFalse(sheet.with_name(sheet.name + ".sampling.json").exists())
            self.assertFalse(sheet.parent.exists())

    def test_evaluate_cli_rejects_a_prefixed_label_with_exit_2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            run(FIXTURE, run_dir)
            draw_sample(run_dir, root / "sheet.csv", 4, candidates=5, negatives=0)
            plan = json.loads((root / "sheet.csv.sampling.json").read_text(encoding="utf-8"))
            labels = root / "labels.csv"
            with labels.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=ADJUDICATED_FIELDS, lineterminator="\n")
                writer.writeheader()
                for unit in plan["key"]:
                    writer.writerow({
                        "sample_id": unit["sample_id"],
                        "label": "'unknown",
                        "evidence_level": "L2",
                        "duration_judgement": "not_assessable",
                        "true_start_utc": "",
                        "true_end_utc": "",
                        "adjudicator_id": "J1",
                    })
            out = root / "eval.json"
            stderr = io.StringIO()
            argv = ["harborlens-evaluate", "--run", str(run_dir),
                    "--sampling", str(root / "sheet.csv.sampling.json"),
                    "--labels", str(labels), "--out", str(out)]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    evaluate_main()
            self.assertEqual(caught.exception.code, 2)
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertIn("not converted", stderr.getvalue())
            self.assertFalse(out.exists())
            self.assertFalse(out.with_name(out.name + ".partial").exists())

    def test_draw_sample_neutralizes_vessel_type_and_keeps_negative_longitude(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "in.csv"
            with source.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADER)
                writer.writerows(track("199010041", "=cmd", 0) + track("199010042", "  =cmd", 1))
            run_dir = root / "run"
            run(source, run_dir, window_start="2024-01-02T00:00:00Z", window_end="2024-01-02T12:00:00Z")
            sheet = root / "labels.csv"
            record = draw_sample(run_dir, sheet, 11, candidates=10, negatives=0)
            self.assertGreaterEqual(record["drawn"]["candidates"], 2)
            with sheet.open(newline="", encoding="utf-8") as handle:
                raw = list(csv.DictReader(handle))
            modes = {row["vessel_type_mode"] for row in raw}
            self.assertEqual(modes, {"'=cmd", "'  =cmd"})
            for row in raw:
                self.assertTrue(row["centroid_lon"].startswith("-"), row["centroid_lon"])
                self.assertFalse(row["centroid_lon"].startswith("'"))
                self.assertNotIn("'", row["mmsi"])
                self.assertNotIn("'", row["start_utc"])
            filled = []
            for row in raw:
                # The sheet already stores the prefixed cell. The writer takes the
                # logical value, so recover it before rendering the completed sheet.
                filled.append({**row,
                               "vessel_type_mode": recover_text_cell(row["vessel_type_mode"]),
                               "annotator_id": "A1", "label": "unknown", "confidence": "low",
                               "evidence_level": "L2", "evidence_sources": "ais_track",
                               "fragment_of_longer_stop": "unknown", "duration_judgement": "not_assessable",
                               "notes": "=note"})
            # notes are neutralized by the same renderer the sampler uses.
            completed = write_rendered(root / "done.csv", filled)
            _who, labels = _read_sheet(completed)
            self.assertEqual({row["vessel_type_mode"] for row in labels.values()}, {"=cmd", "  =cmd"})
            self.assertTrue(all(row["notes"] == "=note" for row in labels.values()))
            csvs = sorted(path.name for path in sheet.parent.glob("*.csv"))
            self.assertIn("labels.csv", csvs)
            self.assertTrue(sheet.with_name(sheet.name + ".sampling.json").is_file())
            self.assertFalse(sheet.with_name(sheet.name + ".key.csv").exists())
            self.assertEqual(WARNING, record["warning"])
            self.assertNotIn("accuracy", record["warning"])

    def test_synthetic_fixture_sheet_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            run(FIXTURE, run_dir)
            sheet = root / "sheet.csv"
            draw_sample(run_dir, sheet, 20241112)
            body = sheet.read_bytes()
            self.assertEqual(body, FIXTURE_SHEET.encode("utf-8"))
            self.assertEqual(hashlib.sha256(body).hexdigest(), FIXTURE_SHEET_SHA256)
            self.assertNotIn(b"'", body)
            self.assertIn(b",-95.159998,", body)
            self.assertFalse(list(sheet.parent.glob("*.key.csv")))
            self.assertTrue(sheet.with_name("sheet.csv.sampling.json").is_file())


if __name__ == "__main__":
    unittest.main()
