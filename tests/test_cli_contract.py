"""CLI exit codes, help text and --version for the research commands.

Expected domain errors exit 2 through argparse, with no traceback unless
--debug is set. --debug still exits 2. A bug still propagates. KeyboardInterrupt
is not caught. Synthetic fixtures only.
"""
import contextlib
import hashlib
import importlib
import inspect
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harborlens import __version__
from harborlens.ais import REQUIRED_COLUMNS, header_alias
from harborlens.censoring import AnalysisWindowError, declared_window
from harborlens.cli import main as harborlens_main
from harborlens.evaluation import _read_labels, evaluate, main as evaluate_main
from harborlens.labeling import (
    agreement, agreement_main, candidate_feature_collection, candidate_identity_shape,
    draw_sample, sample_main,
)
from harborlens.multiday import main as multiday_main
from harborlens.sensitivity import main as sensitivity_main
from harborlens.fr_timeline import main as fr_main
from harborlens.io_safe import AISInputError
from harborlens.provenance import main as verify_main
from harborlens.segmentation import SegmentationParams

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais.csv"


def console_scripts():
    """Names and ``module:function`` targets from ``[project.scripts]``."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    section = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    scripts = {}
    for line in section.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, target = line.split("=", 1)
        scripts[name.strip()] = target.strip().strip('"').strip("'")
    return scripts


def _invoke(main, argv):
    stderr = io.StringIO()
    stdout = io.StringIO()
    with mock.patch.object(sys, "argv", argv), \
            contextlib.redirect_stderr(stderr), \
            contextlib.redirect_stdout(stdout):
        try:
            main()
        except SystemExit as caught:
            code = 0 if caught.code is None else caught.code
        else:
            code = 0
    return code, stdout.getvalue(), stderr.getvalue()


class ColumnMessageTests(unittest.TestCase):
    def test_required_column_order(self):
        self.assertEqual(REQUIRED_COLUMNS, ("mmsi", "timestamp", "lat", "lon", "sog"))

    def test_first_missing_required_column_is_named(self):
        with self.assertRaises(AISInputError) as caught:
            header_alias(["not", "a", "valid", "ais"], "mmsi", source="/tmp/garbage.csv")
        message = str(caught.exception)
        self.assertIn("input file '/tmp/garbage.csv' is missing required column 'mmsi'", message)
        self.assertIn("(found: not, a, valid, ais)", message)
        self.assertIn("Expected required AIS columns: mmsi, timestamp, lat, lon, sog", message)

    def test_later_missing_column_waits_its_turn(self):
        self.assertEqual(header_alias(["MMSI", "lat"], "mmsi", source="x.csv"), "MMSI")
        with self.assertRaisesRegex(AISInputError, "missing required column 'timestamp'"):
            header_alias(["MMSI", "lat"], "timestamp", source="x.csv")

    def test_header_controls_are_escaped_and_capped(self):
        hostile = ["\x1b[31m", "\x1b]0;PWNED\x07", "\u202e", "A" * 50]
        hostile.extend(f"col{i}" for i in range(12))
        with self.assertRaises(AISInputError) as caught:
            header_alias(hostile, "mmsi", source="x.csv")
        message = str(caught.exception)
        self.assertNotIn("\x1b", message)
        self.assertNotIn("\x07", message)
        self.assertNotIn("\u202e", message)
        self.assertIn("\\x1b", message)
        self.assertIn("\\x07", message)
        self.assertIn("\\u202e", message)
        self.assertIn("... (+6 more)", message)
        self.assertIn("A" * 40 + "...", message)
        self.assertNotIn("A" * 41, message)
        self.assertLess(len(message), 2000)


class HarborlensCliTests(unittest.TestCase):
    def test_help_and_version_do_not_need_input(self):
        code, out, err = _invoke(harborlens_main, ["harborlens", "--help"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        for fragment in (
            "NOT FOR NAVIGATION",
            "default: results",
            "-95.7",
            "Houston",
            "default: 0.5",
            "default: 30",
            "default: 15",
            "default: 1000",
            "default: 8",
            "default: 65",
            "tests/fixtures/synthetic_ais.csv",
            "harborlens-verify --manifest",
            "print a traceback after a domain error (still exit 2)",
        ):
            self.assertIn(fragment, out, fragment)
        defaults = SegmentationParams()
        self.assertEqual(defaults.max_sog_knots, 0.5)
        self.assertEqual(defaults.min_duration_minutes, 30)
        self.assertEqual(defaults.max_gap_minutes, 15)
        self.assertEqual(defaults.max_radius_m, 1000)
        self.assertEqual(defaults.min_points, 8)
        self.assertEqual(defaults.max_jump_knots, 65)

        code, out, err = _invoke(harborlens_main, ["harborlens", "--version"])
        self.assertEqual((code, out, err), (0, f"harborlens {__version__}\n", ""))
        code, out, err = _invoke(harborlens_main, ["harborlens", "-V"])
        self.assertEqual((code, out, err), (0, f"harborlens {__version__}\n", ""))

    def test_argparse_errors_keep_their_text(self):
        code, out, err = _invoke(harborlens_main, ["harborlens"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("the following arguments are required: --input", err)
        self.assertNotIn("Traceback", err)

        # A missing required option is reported before an unknown flag.
        # That order is argparse's existing behaviour.
        code, out, err = _invoke(harborlens_main, ["harborlens", "--nope"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("the following arguments are required: --input", err)
        self.assertNotIn("Traceback", err)
        code, out, err = _invoke(harborlens_main, ["harborlens", "--input", "x.csv", "--nope"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("unrecognized arguments: --nope", err)
        self.assertNotIn("Traceback", err)

        code, out, err = _invoke(
            harborlens_main, ["harborlens", "--input", "x.csv", "--max-rows", "abc"],
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("invalid int value: 'abc'", err)
        self.assertNotIn("Traceback", err)

    def test_missing_empty_and_bad_header_exit_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            missing_input = root / "does-not-exist-harborlens.csv"
            missing = root / "missing-out"
            code, out, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(missing_input), "--out", str(missing),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn(
                f"harborlens: error: cannot read input file '{missing_input}' "
                "(No such file or directory).",
                err,
            )
            self.assertIn("tests/fixtures/synthetic_ais.csv", err)
            self.assertNotIn("Traceback", err)
            self.assertNotIn("FileNotFoundError", err)
            self.assertFalse(missing.exists())

            empty = root / "empty.csv"
            empty.write_bytes(b"")
            empty_out = root / "empty-out"
            code, out, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(empty), "--out", str(empty_out),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn(f"harborlens: error: input file '{empty}' is empty.", err)
            self.assertIn("tests/fixtures/synthetic_ais.csv", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(empty_out.exists())

            garbage = root / "garbage.csv"
            garbage.write_text("not,a,valid,ais\n1,2,3,4\n", encoding="utf-8")
            garbage_out = root / "garbage-out"
            code, out, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(garbage), "--out", str(garbage_out),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn(f"input file '{garbage}' is missing required column 'mmsi'", err)
            self.assertIn("Expected required AIS columns: mmsi, timestamp, lat, lon, sog", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(garbage_out.exists())

    def test_debug_keeps_the_message_and_adds_a_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            missing_input = Path(folder) / "does-not-exist-harborlens.csv"
            out = Path(folder) / "debug-out"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--debug", "--input", str(missing_input),
                "--out", str(out),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(
                f"harborlens: error: cannot read input file '{missing_input}' "
                "(No such file or directory).",
                err,
            )
            self.assertIn("Traceback", err)
            self.assertLess(
                err.index("harborlens: error:"),
                err.index("Traceback"),
            )
            self.assertFalse(out.exists())

    def test_debug_does_not_change_a_successful_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plain = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(root / "plain"),
            ])
            debug = _invoke(harborlens_main, [
                "harborlens", "--debug", "--input", str(FIXTURE), "--out", str(root / "debug"),
            ])
            self.assertEqual(plain[0], 0)
            self.assertEqual(debug[0], 0)
            self.assertEqual(plain[2], "")
            self.assertEqual(debug[2], "")
            left = json.loads(plain[1])
            right = json.loads(debug[1])
            self.assertEqual(left["events"]["stationary_candidates"], 1)
            self.assertIn("unvalidated", left["events"]["warning"])
            self.assertEqual(left["run_id"], right["run_id"])
            self.assertEqual(left["code_version"]["package_version"], __version__)
            for name in ("houston_clean.csv", "stationary_candidates.csv", "stationary_candidates.geojson"):
                self.assertEqual((root / "plain" / name).read_bytes(), (root / "debug" / name).read_bytes(), name)
            left["input_file"] = right["input_file"] = "INPUT"
            left["output"] = right["output"] = "OUTPUT"
            self.assertEqual(left, right)

    def test_stderr_drops_header_controls_and_keeps_a_previous_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            hostile = root / "hostile.csv"
            names = ["\x1b[31m", "\x1b]0;PWNED\x07"] + [f"n{i:02d}" for i in range(100)]
            hostile.write_text(",".join(names) + "\n1\n", encoding="utf-8")
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(hostile), "--out", str(root / "hostile-out"),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertNotIn("\x1b", err)
            self.assertNotIn("\x07", err)
            self.assertIn("\\x1b", err)
            self.assertIn("... (+92 more)", err)
            self.assertLess(len(err), 8000)
            self.assertFalse((root / "hostile-out").exists())

            out = root / "out"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
            ])
            self.assertEqual(code, 0, err)
            before = {path.name: path.read_bytes() for path in out.iterdir() if path.is_file()}
            bad = root / "bad.csv"
            bad.write_text(
                "MMSI,BaseDateTime,LAT,LON,SOG\n"
                "199080001,2024-01-02T00:00:00Z,29.7,-95.1,0.1\n"
                "199080001,2024-01-02T00:01:00Z,29.7,-95.1,0.1,EXTRA\n",
                encoding="utf-8",
            )
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(bad), "--out", str(out),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertNotIn("Traceback", err)
            self.assertIn("more values than header", err)
            after = {path.name: path.read_bytes() for path in out.iterdir() if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(any(name.endswith(".partial") for name in after))
            code, stdout, err = _invoke(verify_main, [
                "harborlens-verify", "--manifest", str(out / "manifest.json"),
            ])
            self.assertEqual(code, 0, err)
            self.assertIn('"ok": true', stdout)

    @unittest.skipUnless(hasattr(os, "symlink"), "os.symlink is not available")
    def test_planted_partial_symlink_and_file_are_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            out = root / "out"
            out.mkdir()
            victim_link = root / "victim-link.txt"
            victim_file = root / "victim-file.txt"
            victim_target = root / "victim-target.txt"
            victim_link.write_text("LINK-SECRET", encoding="utf-8")
            victim_file.write_text("FILE-SECRET", encoding="utf-8")
            victim_target.write_text("TARGET-SECRET", encoding="utf-8")
            planted_file = out / "manifest.json.partial"
            planted_file.write_text("REGULAR-PARTIAL", encoding="utf-8")
            try:
                (out / "houston_clean.csv.partial").symlink_to(victim_link)
                (out / "stationary_candidates.csv").symlink_to(victim_target)
            except OSError as exc:
                self.skipTest(f"symlink is not supported: {exc}")
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
            ])
            self.assertEqual(code, 0, err)
            self.assertEqual(victim_link.read_text(encoding="utf-8"), "LINK-SECRET")
            self.assertEqual(victim_file.read_text(encoding="utf-8"), "FILE-SECRET")
            self.assertEqual(victim_target.read_text(encoding="utf-8"), "TARGET-SECRET")
            self.assertEqual(planted_file.read_text(encoding="utf-8"), "REGULAR-PARTIAL")
            self.assertTrue((out / "houston_clean.csv.partial").is_symlink())
            cleaned = (out / "houston_clean.csv").read_bytes()
            self.assertEqual(
                hashlib.sha256(cleaned).hexdigest(),
                "4cd3986411530eef4296bcc2a964ab978f11925468bce8e67600c11c4aad1b75",
            )
            self.assertNotIn(b"TARGET-SECRET", cleaned)
            self.assertFalse((out / "stationary_candidates.csv").is_symlink())
            code, stdout, err = _invoke(verify_main, [
                "harborlens-verify", "--manifest", str(out / "manifest.json"),
            ])
            self.assertEqual(code, 0, err)
            self.assertIn('"ok": true', stdout)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory write bits")
    def test_unwritable_output_directory_exits_2(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "locked"
            out.mkdir()
            out.chmod(0o500)
            try:
                code, stdout, err = _invoke(harborlens_main, [
                    "harborlens", "--input", str(FIXTURE), "--out", str(out),
                ])
            finally:
                out.chmod(0o700)
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(f"cannot write output directory '{out}'", err)
            self.assertIn("Permission denied", err)
            self.assertNotIn("Traceback", err)

    def test_main_does_not_catch_broad_errors(self):
        source = inspect.getsource(harborlens_main)
        self.assertNotIn("except Exception", source)
        self.assertNotIn("except ValueError", source)
        self.assertNotIn("except KeyboardInterrupt", source)
        self.assertIn("except AISInputError", source)


class EvaluateAndVerifyCliTests(unittest.TestCase):
    def test_missing_run_manifest_exits_2_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder) / "does-not-exist-run"
            out = Path(folder) / "eval.json"
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate",
                "--run", str(run_dir),
                "--sampling", str(Path(folder) / "does-not-exist.sampling.json"),
                "--labels", str(Path(folder) / "does-not-exist.csv"),
                "--out", str(out),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(
                "harborlens-evaluate: error: cannot read run manifest "
                f"'{run_dir / 'manifest.json'}' (No such file or directory).",
                err,
            )
            self.assertNotIn("Traceback", err)
            self.assertNotIn("FileNotFoundError", err)
            self.assertFalse(out.exists())

    def test_rejected_label_provenance_debug_prints_a_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "eval.json"
            argv = [
                "harborlens-evaluate",
                "--run", str(Path(folder) / "missing-run"),
                "--sampling", str(Path(folder) / "missing.sampling.json"),
                "--labels", str(Path(folder) / "missing-labels.csv"),
                "--out", str(out),
                "--label-provenance", "real-labels",
                "--debug",
            ]
            code, stdout, err = _invoke(evaluate_main, argv)
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("label_provenance must be synthetic or unspecified", err)
            self.assertIn("Traceback", err)
            self.assertLess(err.index("error:"), err.index("Traceback"))
            self.assertFalse(out.exists())

    def test_invalid_manifest_sampling_and_geojson_exit_2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            manifest = run_dir / "manifest.json"
            original = manifest.read_bytes()
            for body in (b"{bad", b"[]", b"\xff"):
                manifest.write_bytes(body)
                code, stdout, err = _invoke(verify_main, [
                    "harborlens-verify", "--manifest", str(manifest),
                ])
                self.assertEqual(code, 2, body)
                self.assertEqual(stdout, "")
                self.assertIn(
                    f"manifest '{manifest}' is not a valid HarborLens manifest", err,
                )
                self.assertNotIn("Traceback", err)
                code, stdout, err = _invoke(evaluate_main, [
                    "harborlens-evaluate", "--run", str(run_dir),
                    "--sampling", str(root / "missing.sampling.json"),
                    "--labels", str(root / "missing-labels.csv"),
                    "--out", str(root / "eval.json"),
                    "--label-provenance", "synthetic",
                ])
                self.assertEqual(code, 2, body)
                self.assertEqual(stdout, "")
                self.assertIn(
                    f"manifest '{manifest}' is not a valid HarborLens manifest", err,
                )
                self.assertNotIn("Traceback", err)
            manifest.write_bytes(original)

            sampling = root / "broken.sampling.json"
            sampling.write_text("{bad", encoding="utf-8")
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling),
                "--labels", str(root / "missing-labels.csv"),
                "--out", str(root / "eval.json"),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(f"sampling file '{sampling}' is not valid JSON", err)
            self.assertNotIn("Traceback", err)
            sampling.write_bytes(b"\xff")
            code, _, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling),
                "--labels", str(root / "missing-labels.csv"),
                "--out", str(root / "eval.json"),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertIn(f"sampling file '{sampling}' is not valid UTF-8", err)
            self.assertNotIn("not valid JSON", err)
            self.assertNotIn("Traceback", err)

            sheet = root / "sheet.csv"
            draw_sample(run_dir, sheet, 7, candidates=1, negatives=0)
            labels = root / "labels.csv"
            sampling_path = Path(str(sheet) + ".sampling.json")
            plan = json.loads(sampling_path.read_text(encoding="utf-8"))
            with labels.open("w", newline="", encoding="utf-8") as handle:
                handle.write(
                    "sample_id,label,evidence_level,duration_judgement,"
                    "true_start_utc,true_end_utc,adjudicator_id\n"
                )
                for unit in plan["key"]:
                    handle.write(f"{unit['sample_id']},unknown,L2,not_assessable,,,J1\n")
            geo = run_dir / "stationary_candidates.geojson"

            def point_manifest_at(payload):
                geo.write_bytes(payload)
                record = json.loads(manifest.read_text(encoding="utf-8"))
                record["artifacts"]["stationary_candidates.geojson"] = {
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                }
                manifest.write_text(json.dumps(record), encoding="utf-8")
                plan["run_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
                sampling_path.write_text(json.dumps(plan), encoding="utf-8")

            point_manifest_at(b"{bad")
            with self.assertRaises(AISInputError) as caught:
                evaluate(run_dir, sampling_path, labels, root / "geo.json",
                         label_provenance="synthetic")
            self.assertEqual(
                str(caught.exception),
                f"candidate GeoJSON '{geo}' is not valid JSON",
            )
            point_manifest_at(b"\xff")
            with self.assertRaises(AISInputError) as caught:
                evaluate(run_dir, sampling_path, labels, root / "geo-utf8.json",
                         label_provenance="synthetic")
            self.assertIn("is not valid UTF-8", str(caught.exception))
            self.assertNotIn("not valid JSON", str(caught.exception))
            for payload in (b"[]", b"null", b"1"):
                point_manifest_at(payload)
                with self.assertRaises(AISInputError) as caught:
                    evaluate(run_dir, sampling_path, labels, root / "geo-shape.json",
                             label_provenance="synthetic")
                self.assertEqual(
                    str(caught.exception),
                    f"candidate GeoJSON '{geo}' is valid JSON but has the wrong shape",
                )
                self.assertNotIn("not valid JSON", str(caught.exception))
            sampling.write_text("[]", encoding="utf-8")
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling),
                "--labels", str(labels),
                "--out", str(root / "shape.json"),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(
                f"sampling file '{sampling}' is valid JSON but has the wrong shape", err,
            )
            self.assertNotIn("not valid JSON", err)
            self.assertNotIn("Traceback", err)

    def test_control_in_input_path_is_escaped_on_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            missing = root / "no\x1bpe.csv"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(missing), "--out", str(root / "out"),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertNotIn("\x1b", err)
            self.assertIn("\\x1b", err)
            self.assertIn("cannot read input file", err)

    def test_label_sample_bad_manifest_exits_2(self):
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder) / "run"
            run_dir.mkdir()
            manifest = run_dir / "manifest.json"
            manifest.write_text("[]", encoding="utf-8")
            code, stdout, err = _invoke(sample_main, [
                "harborlens-label-sample", "--run", str(run_dir),
                "--sheet", str(Path(folder) / "sheet.csv"), "--seed", "1",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(
                f"manifest '{manifest}' is not a valid HarborLens manifest", err,
            )
            self.assertNotIn("Traceback", err)

    def test_unreadable_artifact_stays_a_verification_result(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
            ])
            self.assertEqual(code, 0, err)
            from harborlens.provenance import checksum as real_checksum

            def boom(path):
                if Path(path).name == "houston_clean.csv":
                    raise PermissionError(13, "Permission denied", str(path))
                return real_checksum(path)

            with mock.patch("harborlens.provenance.checksum", boom):
                code, stdout, err = _invoke(verify_main, [
                    "harborlens-verify", "--manifest", str(out / "manifest.json"),
                ])
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", err)
            body = json.loads(stdout)
            self.assertFalse(body["ok"])
            self.assertEqual(body["artifacts"]["houston_clean.csv"], "unreadable")

    def test_rejected_label_provenance_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "eval.json"
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate",
                "--run", "/tmp/does-not-exist-run",
                "--sampling", "/tmp/missing.sampling.json",
                "--labels", "/tmp/missing-labels.csv",
                "--out", str(out),
                "--label-provenance", "real-labels",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("label_provenance must be synthetic or unspecified", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(out.exists())

    def test_evaluate_debug_on_a_missing_sampling_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, _ = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0)
            out = root / "eval.json"
            sampling = root / "missing.sampling.json"
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--debug",
                "--run", str(run_dir),
                "--sampling", str(sampling),
                "--labels", str(root / "missing-labels.csv"),
                "--out", str(out),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(f"cannot read sampling file '{sampling}' (No such file or directory).", err)
            self.assertIn("Traceback", err)
            self.assertFalse(out.exists())

    def test_verify_help_version_and_missing_manifest(self):
        code, out, err = _invoke(verify_main, ["harborlens-verify", "--version"])
        self.assertEqual((code, out, err), (0, f"harborlens-verify {__version__}\n", ""))
        code, out, err = _invoke(verify_main, ["harborlens-verify", "-V"])
        self.assertEqual((code, out, err), (0, f"harborlens-verify {__version__}\n", ""))
        code, out, err = _invoke(verify_main, ["harborlens-verify", "--help"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("manifest.json", out)
        self.assertIn("SHA-256", out)

        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "missing" / "manifest.json"
            code, stdout, err = _invoke(verify_main, [
                "harborlens-verify", "--manifest", str(manifest),
            ])
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn(
            f"harborlens-verify: error: cannot read manifest '{manifest}' "
            "(No such file or directory).",
            err,
        )
        self.assertIn("Give --manifest the manifest.json written by harborlens.", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("{", stdout)

    def test_verify_hash_mismatch_stays_exit_1_with_json(self):
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder) / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            cleaned = run_dir / "houston_clean.csv"
            cleaned.write_bytes(cleaned.read_bytes() + b"\n")
            code, stdout, err = _invoke(verify_main, [
                "harborlens-verify", "--manifest", str(run_dir / "manifest.json"),
            ])
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", err)
            body = json.loads(stdout)
            self.assertFalse(body["ok"])
            self.assertEqual(body["artifacts"]["houston_clean.csv"], "mismatch")

    def test_missing_labels_message_names_the_path(self):
        missing = Path("/tmp/missing-labels.csv")
        with self.assertRaises(AISInputError) as caught:
            _read_labels(missing, set())
        self.assertEqual(
            str(caught.exception),
            f"cannot read labels file '{missing}' (No such file or directory).",
        )

    def test_mains_do_not_catch_broad_errors(self):
        for function in (evaluate_main, verify_main, fr_main):
            source = inspect.getsource(function)
            self.assertNotIn("except Exception", source)
            self.assertNotIn("except ValueError", source)
            self.assertNotIn("except KeyboardInterrupt", source)


class ConsoleScriptVersionTests(unittest.TestCase):
    def test_every_console_script_answers_version(self):
        scripts = console_scripts()
        self.assertEqual(len(scripts), 20)
        self.assertIn("harborlens", scripts)
        self.assertIn("harborlens-verify", scripts)
        self.assertIn("harborlens-evaluate", scripts)
        self.assertIn("harborlens-fr-timeline", scripts)
        for name, target in scripts.items():
            module_name, func_name = target.split(":")
            function = getattr(importlib.import_module(module_name), func_name)
            with self.subTest(script=name):
                code, out, err = _invoke(function, [name, "--version"])
                self.assertEqual(code, 0)
                self.assertEqual(out, f"{name} {__version__}\n")
                self.assertEqual(err, "")
                code, out, err = _invoke(function, [name, "-V"])
                self.assertEqual(code, 0)
                self.assertEqual(out, f"{name} {__version__}\n")
                self.assertEqual(err, "")


_SOURCE_URL_ERROR = (
    "source URL must be http or https, must name a host, and must not include credentials"
)


class SourceUrlAndGeoJsonShapeTests(unittest.TestCase):
    """PR #99 follow-ups: invalid source URLs and GeoJSON shape exit 2.

    Synthetic fixture only. A stationary candidate is not a berth, anchorage,
    wait, or port call.
    """

    def test_invalid_source_url_exits_2_without_a_traceback(self):
        cases = (
            "ftp://x", "", "http://", "https://user:secret@example.org",
            "http://[::1", "http://[",
        )
        for url in cases:
            with self.subTest(url=url):
                with tempfile.TemporaryDirectory() as folder:
                    out = Path(folder) / "out"
                    code, stdout, err = _invoke(harborlens_main, [
                        "harborlens", "--input", str(FIXTURE), "--out", str(out),
                        "--source-url", url,
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(_SOURCE_URL_ERROR, err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())

    def test_invalid_source_url_debug_still_exits_2(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
                "--source-url", "ftp://x", "--debug",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(_SOURCE_URL_ERROR, err)
            self.assertIn("Traceback", err)
            self.assertLess(err.index("error:"), err.index("Traceback"))
            self.assertFalse(out.exists())

    def test_https_source_url_exits_0_and_stays_review_required(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
                "--source-url", "https://example.org/ais.csv",
            ])
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            body = json.loads(stdout)
            self.assertEqual(body["source_metadata"]["source_url"], "https://example.org/ais.csv")
            self.assertEqual(body["source_metadata"]["metadata_origin"], "user_declared")
            self.assertEqual(body["source_metadata"]["rights_status"], "review_required")
            self.assertTrue((out / "manifest.json").is_file())

    def test_http_source_url_is_the_accepted_scheme_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
                "--source-url", "http://example.org",
            ])
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(stdout)["source_metadata"]["source_url"], "http://example.org")
            self.assertEqual(json.loads(stdout)["source_metadata"]["rights_status"], "review_required")

    def test_candidate_feature_collection_shape_boundaries(self):
        path = Path("synthetic.geojson")
        point = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-95.0, 29.5]},
            "properties": {"event_id": "abc"},
        }
        accepted = candidate_feature_collection(
            {"type": "FeatureCollection", "features": [point]}, path,
        )
        self.assertEqual(accepted[0]["geometry"]["coordinates"][:2], [-95.0, 29.5])
        self.assertEqual(
            candidate_feature_collection({"type": "FeatureCollection", "features": []}, path),
            [],
        )
        with_altitude = dict(point)
        with_altitude["geometry"] = {"type": "Point", "coordinates": [-95, 29, 0]}
        self.assertEqual(
            len(candidate_feature_collection(
                {"type": "FeatureCollection", "features": [with_altitude]}, path,
            )),
            1,
        )
        rejected = {
            "features not a list": {"type": "FeatureCollection", "features": {"type": "Feature"}},
            "feature is not an object": {"type": "FeatureCollection", "features": [1]},
            "feature without geometry": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {"event_id": "abc"}}],
            },
            "coordinates are a string": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": "nope"},
                    "properties": {"event_id": "abc"},
                }],
            },
            "coordinates are one number": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-95.0]},
                    "properties": {"event_id": "abc"},
                }],
            },
            "top-level array": [],
        }
        for name, document in rejected.items():
            with self.subTest(shape=name):
                with self.assertRaises(AISInputError) as caught:
                    candidate_feature_collection(document, path)
                self.assertIn("valid JSON but has the wrong shape", str(caught.exception))
                self.assertNotIn("not valid JSON", str(caught.exception))

    def test_geojson_inner_shape_and_json_text_exit_2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            manifest = run_dir / "manifest.json"
            original_manifest = manifest.read_bytes()
            geo = run_dir / "stationary_candidates.geojson"
            original_geo = geo.read_bytes()
            sheet = root / "sheet.csv"
            draw_sample(run_dir, sheet, 7, candidates=1, negatives=0)
            labels = root / "labels.csv"
            sampling_path = Path(str(sheet) + ".sampling.json")
            plan = json.loads(sampling_path.read_text(encoding="utf-8"))
            with labels.open("w", newline="", encoding="utf-8") as handle:
                handle.write(
                    "sample_id,label,evidence_level,duration_judgement,"
                    "true_start_utc,true_end_utc,adjudicator_id\n"
                )
                for unit in plan["key"]:
                    handle.write(f"{unit['sample_id']},unknown,L2,not_assessable,,,J1\n")

            def point_manifest_at(payload):
                geo.write_bytes(payload)
                record = json.loads(manifest.read_text(encoding="utf-8"))
                record["artifacts"]["stationary_candidates.geojson"] = {
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                }
                manifest.write_text(json.dumps(record), encoding="utf-8")
                plan["run_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
                sampling_path.write_text(json.dumps(plan), encoding="utf-8")

            shapes = {
                "features not a list": b'{"type":"FeatureCollection","features":{"type":"Feature"}}',
                "feature without geometry": (
                    b'{"type":"FeatureCollection","features":[{"type":"Feature",'
                    b'"properties":{"event_id":"abc"}}]}'
                ),
                "wrong coordinates type": (
                    b'{"type":"FeatureCollection","features":[{"type":"Feature",'
                    b'"geometry":{"type":"Point","coordinates":"nope"},'
                    b'"properties":{"event_id":"abc"}}]}'
                ),
            }
            for name, payload in shapes.items():
                with self.subTest(shape=name):
                    point_manifest_at(payload)
                    out = root / f"{name.replace(' ', '-')}.json"
                    code, stdout, err = _invoke(evaluate_main, [
                        "harborlens-evaluate", "--run", str(run_dir),
                        "--sampling", str(sampling_path),
                        "--labels", str(labels),
                        "--out", str(out),
                        "--label-provenance", "synthetic",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(
                        f"candidate GeoJSON '{geo}' is valid JSON but has the wrong shape",
                        err,
                    )
                    self.assertNotIn("not valid JSON", err)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())
                    sheet_out = root / f"{name.replace(' ', '-')}.csv"
                    code, stdout, err = _invoke(sample_main, [
                        "harborlens-label-sample", "--run", str(run_dir),
                        "--sheet", str(sheet_out), "--seed", "3",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(
                        f"candidate GeoJSON '{geo}' is valid JSON but has the wrong shape",
                        err,
                    )
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(sheet_out.exists())

            point_manifest_at(b"{bad")
            out = root / "not-json.json"
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling_path),
                "--labels", str(labels),
                "--out", str(out),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(f"candidate GeoJSON '{geo}' is not valid JSON", err)
            self.assertNotIn("wrong shape", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(out.exists())

            broken = root / "broken.sampling.json"
            broken.write_text("{bad", encoding="utf-8")
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(broken),
                "--labels", str(labels),
                "--out", str(root / "sampling-text.json"),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertIn(f"sampling file '{broken}' is not valid JSON", err)
            self.assertNotIn("wrong shape", err)
            self.assertNotIn("Traceback", err)

            point_manifest_at(
                b'{"type":"FeatureCollection","features":[]}'
            )
            out = root / "empty-features.json"
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling_path),
                "--labels", str(labels),
                "--out", str(out),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(json.loads(stdout)["validation_status"], "unvalidated")
            self.assertTrue(out.is_file())
            with labels.open("w", newline="", encoding="utf-8") as handle:
                handle.write(
                    "sample_id,label,evidence_level,duration_judgement,"
                    "true_start_utc,true_end_utc,adjudicator_id\n"
                )
                for unit in plan["key"]:
                    label = "at_berth" if unit["kind"] == "candidate" else "transit"
                    handle.write(f"{unit['sample_id']},{label},L2,not_assessable,,,J1\n")
            missing = root / "missing-candidate.json"
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling_path),
                "--labels", str(labels),
                "--out", str(missing),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("is not in the run", err)
            self.assertNotIn("wrong shape", err)
            self.assertNotIn("not valid JSON", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(missing.exists())

            geo.write_bytes(original_geo)
            manifest.write_bytes(original_manifest)
            fresh = draw_sample(run_dir, root / "fresh.csv", 7, candidates=1, negatives=0)
            self.assertEqual(fresh["rights_status"], "review_required")
            self.assertGreaterEqual(fresh["drawn"]["candidates"], 1)

    def test_label_commands_escape_controls_in_paths(self):
        controls = (
            ("esc", "\x1b", "\\x1b"),
            ("newline", "\n", "\\x0a"),
            ("cr", "\r", "\\x0d"),
            ("bidi", "\u202e", "\\u202e"),
            ("line_separator", "\u2028", "\\u2028"),
            ("c1", "\x85", "\\x85"),
        )
        for name, character, escaped in controls:
            with self.subTest(control=name):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    run_dir = root / f"run{character}x"
                    run_dir.mkdir()
                    (run_dir / "manifest.json").write_text("[]", encoding="utf-8")
                    sheet = root / "sheet.csv"
                    code, stdout, err = _invoke(sample_main, [
                        "harborlens-label-sample", "--run", str(run_dir),
                        "--sheet", str(sheet), "--seed", "1",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    error_lines = [line for line in err.splitlines() if "error:" in line]
                    self.assertEqual(len(error_lines), 1)
                    self.assertIn(escaped, error_lines[0])
                    self.assertNotIn(character, error_lines[0])
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(sheet.exists())

                    bad = root / f"a{character}x.csv"
                    other = root / "b.csv"
                    bad.write_text("not,a,header\n", encoding="utf-8")
                    other.write_text("sample_id,label\nS0001,unknown\n", encoding="utf-8")
                    out = root / "agree.json"
                    code, stdout, err = _invoke(agreement_main, [
                        "harborlens-label-agreement",
                        "--sheets", str(bad), str(other),
                        "--out", str(out),
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    error_lines = [line for line in err.splitlines() if "error:" in line]
                    self.assertEqual(len(error_lines), 1)
                    self.assertIn(escaped, error_lines[0])
                    self.assertNotIn(character, error_lines[0])
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())

    def test_deeply_nested_json_exits_2(self):
        payload = ("[" * 100000) + ("]" * 100000)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            sampling = root / "deep.sampling.json"
            sampling.write_text(payload, encoding="utf-8")
            labels = root / "labels.csv"
            labels.write_text("sample_id\n", encoding="utf-8")
            out = root / "deep.json"
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling),
                "--labels", str(labels),
                "--out", str(out),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(f"sampling file '{sampling}' is not valid JSON", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(out.exists())

            geo = run_dir / "stationary_candidates.geojson"
            raw = payload.encode("utf-8")
            geo.write_bytes(raw)
            manifest = run_dir / "manifest.json"
            record = json.loads(manifest.read_text(encoding="utf-8"))
            record["artifacts"]["stationary_candidates.geojson"] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
            manifest.write_text(json.dumps(record), encoding="utf-8")
            sheet = root / "deep.csv"
            code, stdout, err = _invoke(sample_main, [
                "harborlens-label-sample", "--run", str(run_dir),
                "--sheet", str(sheet), "--seed", "1",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(f"candidate GeoJSON '{geo}' is not valid JSON", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(sheet.exists())

    def test_missing_candidate_property_exits_2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            geo_path = run_dir / "stationary_candidates.geojson"
            manifest = run_dir / "manifest.json"
            original = json.loads(geo_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(original["features"]), 1)

            def publish(document):
                raw = json.dumps(document).encode("utf-8")
                geo_path.write_bytes(raw)
                record = json.loads(manifest.read_text(encoding="utf-8"))
                record["artifacts"]["stationary_candidates.geojson"] = {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
                manifest.write_text(json.dumps(record), encoding="utf-8")

            for key in ("start_utc", "end_utc", "mmsi", "event_id"):
                with self.subTest(missing=key):
                    broken = json.loads(json.dumps(original))
                    del broken["features"][0]["properties"][key]
                    publish(broken)
                    sheet = root / f"missing-{key}.csv"
                    code, stdout, err = _invoke(sample_main, [
                        "harborlens-label-sample", "--run", str(run_dir),
                        "--sheet", str(sheet), "--seed", "1",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(
                        f"candidate GeoJSON '{geo_path}' is valid JSON but has the wrong shape",
                        err,
                    )
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(sheet.exists())
            broken = json.loads(json.dumps(original))
            broken["features"][0]["properties"]["start_utc"] = 1
            publish(broken)
            sheet = root / "bad-start.csv"
            code, stdout, err = _invoke(sample_main, [
                "harborlens-label-sample", "--run", str(run_dir),
                "--sheet", str(sheet), "--seed", "1",
            ])
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", err)
            self.assertIn("wrong shape", err)
            self.assertFalse(sheet.exists())

    def test_non_numeric_frame_counts_exit_2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            labels = root / "labels.csv"
            labels.write_text("sample_id\n", encoding="utf-8")
            sampling = root / "frame.sampling.json"
            for value in ("nope", None, {"n": 1}):
                with self.subTest(value=value):
                    sampling.write_text(json.dumps({
                        "key": [],
                        "frame": {"candidates": {"x": value}},
                    }), encoding="utf-8")
                    out = root / "frame.json"
                    code, stdout, err = _invoke(evaluate_main, [
                        "harborlens-evaluate", "--run", str(run_dir),
                        "--sampling", str(sampling),
                        "--labels", str(labels),
                        "--out", str(out),
                        "--label-provenance", "synthetic",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(
                        f"sampling file '{sampling}' is valid JSON but has the wrong shape",
                        err,
                    )
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())
            sampling.write_text(json.dumps({
                "key": [],
                "frame": {"candidates": {"x": 0}},
            }), encoding="utf-8")
            out = root / "zero.json"
            code, stdout, err = _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling),
                "--labels", str(labels),
                "--out", str(out),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(code, 2)
            self.assertNotIn("wrong shape", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(out.exists())

    def test_source_url_rejects_whitespace_controls_and_bad_ports(self):
        rejected = (
            "http://example.org\t/ais.csv",
            "http://example.org\n/x",
            "http://ex ample.org",
            "http://example.org/path with space",
            "http://exam\x1bple.org",
            "http://example.org\x7f",
            "http://example.org\x80",
            "http://example.org:abc",
            "http://example.org:65536",
            "http://example.org:99999999",
            "http://[::1]:abc",
            "http://[::1]:99999999",
        )
        for url in rejected:
            with self.subTest(url=url):
                with tempfile.TemporaryDirectory() as folder:
                    out = Path(folder) / "out"
                    code, stdout, err = _invoke(harborlens_main, [
                        "harborlens", "--input", str(FIXTURE), "--out", str(out),
                        "--source-url", url,
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(_SOURCE_URL_ERROR, err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn(url, err)
                    self.assertNotIn("Traceback", err)
                    self.assertNotIn("Port out of range", err)
                    self.assertFalse(out.exists())
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
                "--source-url", "http://example.org:65536", "--debug",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(_SOURCE_URL_ERROR, err)
            self.assertIn("Traceback", err)
            self.assertLess(err.index("error:"), err.index("Traceback"))
            self.assertNotIn("Port out of range", err)
            self.assertFalse(out.exists())

    def test_query_string_is_stored_and_stays_review_required(self):
        url = "http://example.org:443/path?q=1"
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("fetched")):
                code, stdout, err = _invoke(harborlens_main, [
                    "harborlens", "--input", str(FIXTURE), "--out", str(out),
                    "--source-url", url,
                ])
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            body = json.loads(stdout)
            self.assertEqual(body["source_metadata"]["source_url"], url)
            self.assertEqual(body["source_metadata"]["metadata_origin"], "user_declared")
            self.assertEqual(body["source_metadata"]["rights_status"], "review_required")
        for rejected in (
            "http://example.org/path?token=example",
            "http://example.org/path#access_token=example",
            "http://example.org:0",
            "http://example.org/\u202e",
        ):
            with self.subTest(url=rejected):
                with tempfile.TemporaryDirectory() as folder:
                    out = Path(folder) / "out"
                    code, stdout, err = _invoke(harborlens_main, [
                        "harborlens", "--input", str(FIXTURE), "--out", str(out),
                        "--source-url", rejected,
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(_SOURCE_URL_ERROR, err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn(rejected, err)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())

    def test_invalid_utf8_is_not_called_invalid_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            labels = root / "labels.csv"
            labels.write_text(
                "sample_id,label,evidence_level,duration_judgement,"
                "true_start_utc,true_end_utc,adjudicator_id\n",
                encoding="utf-8",
            )
            sampling = root / "sample.sampling.json"
            manifest = run_dir / "manifest.json"
            geo = run_dir / "stationary_candidates.geojson"

            def publish_geo(payload):
                geo.write_bytes(payload)
                record = json.loads(manifest.read_text(encoding="utf-8"))
                record["artifacts"]["stationary_candidates.geojson"] = {
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                }
                manifest.write_text(json.dumps(record), encoding="utf-8")

            cases = (
                (b"\xff", "is not valid UTF-8", "not valid JSON"),
                (b"{bad", "is not valid JSON", "not valid UTF-8"),
                (b"", "is not valid JSON", "not valid UTF-8"),
            )
            for payload, present, absent in cases:
                with self.subTest(payload=payload):
                    sampling.write_bytes(payload)
                    out = root / "eval.json"
                    out.unlink(missing_ok=True)
                    code, stdout, err = _invoke(evaluate_main, [
                        "harborlens-evaluate", "--run", str(run_dir),
                        "--sampling", str(sampling),
                        "--labels", str(labels),
                        "--out", str(out),
                        "--label-provenance", "synthetic",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(f"sampling file '{sampling}' {present}", err)
                    self.assertNotIn(absent, err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())

                    publish_geo(payload)
                    sheet = root / "sheet.csv"
                    sheet.unlink(missing_ok=True)
                    code, stdout, err = _invoke(sample_main, [
                        "harborlens-label-sample", "--run", str(run_dir),
                        "--sheet", str(sheet), "--seed", "1",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(f"candidate GeoJSON '{geo}' {present}", err)
                    self.assertNotIn(absent, err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(sheet.exists())

                    out = root / "geo-eval.json"
                    record = json.loads(manifest.read_text(encoding="utf-8"))
                    sampling.write_text(json.dumps({
                        "key": [],
                        "frame": {"candidates": {}},
                        "run_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                        "parameter_set": record["method_parameters"]["parameter_set"],
                    }), encoding="utf-8")
                    code, stdout, err = _invoke(evaluate_main, [
                        "harborlens-evaluate", "--run", str(run_dir),
                        "--sampling", str(sampling),
                        "--labels", str(labels),
                        "--out", str(out),
                        "--label-provenance", "synthetic",
                    ])
                    self.assertEqual(code, 2)
                    self.assertIn(f"candidate GeoJSON '{geo}' {present}", err)
                    self.assertNotIn(absent, err)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())

    def test_candidate_identity_shape_boundaries(self):
        base = {
            "event_id": "abc",
            "mmsi": "199000001",
            "start_utc": "2024-01-02T00:00:00Z",
            "end_utc": "2024-01-02T01:00:00Z",
        }
        self.assertTrue(candidate_identity_shape(dict(base)))
        self.assertTrue(candidate_identity_shape(dict(base, mmsi="19900001")))
        self.assertTrue(candidate_identity_shape(dict(base, mmsi="00000001")))
        for bad in (
            "1990001", "1990000011", "", "199000001 ", "19900000a",
            199000001, True, None, 199000001.0,
        ):
            with self.subTest(mmsi=bad):
                self.assertFalse(candidate_identity_shape(dict(base, mmsi=bad)))
        for key in ("start_utc", "end_utc", "mmsi", "event_id"):
            broken = dict(base)
            del broken[key]
            self.assertFalse(candidate_identity_shape(broken), key)
        self.assertFalse(candidate_identity_shape(dict(base, start_utc=1)))
        self.assertFalse(candidate_identity_shape(dict(base, end_utc=1)))
        self.assertFalse(candidate_identity_shape(dict(base, start_utc="")))
        self.assertFalse(candidate_identity_shape(dict(base, event_id="")))
        self.assertFalse(candidate_identity_shape([]))
        arabic = "".join(chr(0x0660 + int(digit)) for digit in "199000001")
        fullwidth = "".join(chr(0xFF10 + int(digit)) for digit in "199000001")
        self.assertTrue(arabic.isdigit())
        self.assertFalse(arabic.isascii())
        self.assertFalse(candidate_identity_shape(dict(base, mmsi=arabic)))
        self.assertFalse(candidate_identity_shape(dict(base, mmsi=fullwidth)))

    def test_evaluate_rejects_missing_or_non_string_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            geo_path = run_dir / "stationary_candidates.geojson"
            manifest = run_dir / "manifest.json"
            original = json.loads(geo_path.read_text(encoding="utf-8"))
            self.assertIsInstance(original["features"][0]["properties"]["mmsi"], str)
            sheet = root / "sheet.csv"
            draw_sample(run_dir, sheet, 7, candidates=1, negatives=0)
            sampling_path = Path(str(sheet) + ".sampling.json")
            plan = json.loads(sampling_path.read_text(encoding="utf-8"))
            labels = root / "labels.csv"
            with labels.open("w", newline="", encoding="utf-8") as handle:
                handle.write(
                    "sample_id,label,evidence_level,duration_judgement,"
                    "true_start_utc,true_end_utc,adjudicator_id\n"
                )
                for unit in plan["key"]:
                    handle.write(f"{unit['sample_id']},unknown,L2,not_assessable,,,J1\n")

            def publish(document):
                raw = json.dumps(document).encode("utf-8")
                geo_path.write_bytes(raw)
                record = json.loads(manifest.read_text(encoding="utf-8"))
                record["artifacts"]["stationary_candidates.geojson"] = {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
                manifest.write_text(json.dumps(record), encoding="utf-8")
                plan["run_manifest_sha256"] = hashlib.sha256(
                    manifest.read_bytes()
                ).hexdigest()
                sampling_path.write_text(json.dumps(plan), encoding="utf-8")

            def run_evaluate(name):
                out = root / name
                return _invoke(evaluate_main, [
                    "harborlens-evaluate", "--run", str(run_dir),
                    "--sampling", str(sampling_path),
                    "--labels", str(labels),
                    "--out", str(out),
                    "--label-provenance", "synthetic",
                ]), out

            code, stdout, err = run_evaluate("writer.json")[0]
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(stdout)["validation_status"], "unvalidated")

            accepted = (
                ("eight digits", "19900001"),
                ("nine digits", "199000001"),
            )
            for name, mmsi in accepted:
                with self.subTest(mmsi=name):
                    document = json.loads(json.dumps(original))
                    document["features"][0]["properties"]["mmsi"] = mmsi
                    publish(document)
                    code, stdout, err = run_evaluate(f"ok-{name.split()[0]}.json")[0]
                    self.assertEqual(code, 0, err)
                    self.assertEqual(json.loads(stdout)["validation_status"], "unvalidated")
                    sheet_out = root / f"ok-{name.split()[0]}.csv"
                    code, stdout, err = _invoke(sample_main, [
                        "harborlens-label-sample", "--run", str(run_dir),
                        "--sheet", str(sheet_out), "--seed", "1",
                    ])
                    self.assertEqual(code, 0, err)
                    self.assertNotIn("Traceback", err)
                    self.assertTrue(sheet_out.is_file())

            rejected = {
                "missing start_utc": ("start_utc", None),
                "missing end_utc": ("end_utc", None),
                "missing mmsi": ("mmsi", None),
                "integer mmsi": ("mmsi", 199000001),
                "seven digits": ("mmsi", "1990001"),
                "ten digits": ("mmsi", "1990000011"),
                "start_utc integer": ("start_utc", 1),
                "empty start_utc": ("start_utc", ""),
            }
            for name, (key, value) in rejected.items():
                with self.subTest(case=name):
                    document = json.loads(json.dumps(original))
                    props = document["features"][0]["properties"]
                    if value is None:
                        del props[key]
                    else:
                        props[key] = value
                    publish(document)
                    slug = name.replace(" ", "-")
                    (code, stdout, err), out = run_evaluate(f"bad-{slug}.json")
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(
                        f"candidate GeoJSON '{geo_path}' is valid JSON but has the wrong shape",
                        err,
                    )
                    self.assertNotIn("not valid JSON", err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())
                    sheet_out = root / f"bad-{slug}.csv"
                    code, stdout, err = _invoke(sample_main, [
                        "harborlens-label-sample", "--run", str(run_dir),
                        "--sheet", str(sheet_out), "--seed", "1",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(
                        f"candidate GeoJSON '{geo_path}' is valid JSON but has the wrong shape",
                        err,
                    )
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(sheet_out.exists())

    def test_verify_escapes_controls_in_manifest_paths(self):
        controls = (
            ("esc", "\x1b", "\\x1b"),
            ("newline", "\n", "\\x0a"),
            ("cr", "\r", "\\x0d"),
            ("bidi", "\u202e", "\\u202e"),
            ("line_separator", "\u2028", "\\u2028"),
            ("c1", "\x85", "\\x85"),
        )
        for name, character, escaped in controls:
            with self.subTest(control=name):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    missing = root / f"missing{character}x" / "manifest.json"
                    code, stdout, err = _invoke(verify_main, [
                        "harborlens-verify", "--manifest", str(missing),
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    error_lines = [line for line in err.splitlines() if "error:" in line]
                    self.assertEqual(len(error_lines), 1)
                    self.assertIn(escaped, error_lines[0])
                    self.assertNotIn(character, error_lines[0])
                    self.assertIn("cannot read manifest", error_lines[0])
                    self.assertNotIn("Traceback", err)

                    present = root / f"bad{character}x.json"
                    present.write_text("[]", encoding="utf-8")
                    code, stdout, err = _invoke(verify_main, [
                        "harborlens-verify", "--manifest", str(present),
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    error_lines = [line for line in err.splitlines() if "error:" in line]
                    self.assertEqual(len(error_lines), 1)
                    self.assertIn(escaped, error_lines[0])
                    self.assertNotIn(character, error_lines[0])
                    self.assertIn("is not a valid HarborLens manifest", error_lines[0])
                    self.assertNotIn("Traceback", err)

    def test_long_integer_json_exits_2(self):
        huge = '{"x": ' + ("9" * 5000) + "}"
        nested = "[" * 100000 + "]" * 100000
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            labels = root / "labels.csv"
            labels.write_text(
                "sample_id,label,evidence_level,duration_judgement,"
                "true_start_utc,true_end_utc,adjudicator_id\n",
                encoding="utf-8",
            )
            manifest = run_dir / "manifest.json"
            geo = run_dir / "stationary_candidates.geojson"
            sampling = root / "huge.sampling.json"

            def publish_geo(payload):
                raw = payload.encode("utf-8")
                geo.write_bytes(raw)
                record = json.loads(manifest.read_text(encoding="utf-8"))
                record["artifacts"]["stationary_candidates.geojson"] = {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
                manifest.write_text(json.dumps(record), encoding="utf-8")

            for name, payload in (("integer", huge), ("nested", nested)):
                with self.subTest(kind=name):
                    sampling.write_text(payload, encoding="utf-8")
                    out = root / f"{name}.json"
                    out.unlink(missing_ok=True)
                    code, stdout, err = _invoke(evaluate_main, [
                        "harborlens-evaluate", "--run", str(run_dir),
                        "--sampling", str(sampling),
                        "--labels", str(labels),
                        "--out", str(out),
                        "--label-provenance", "synthetic",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(f"sampling file '{sampling}' is not valid JSON", err)
                    self.assertNotIn("not valid UTF-8", err)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())

                    publish_geo(payload)
                    sheet = root / f"{name}.csv"
                    sheet.unlink(missing_ok=True)
                    code, stdout, err = _invoke(sample_main, [
                        "harborlens-label-sample", "--run", str(run_dir),
                        "--sheet", str(sheet), "--seed", "1",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(f"candidate GeoJSON '{geo}' is not valid JSON", err)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(sheet.exists())

                    record = json.loads(manifest.read_text(encoding="utf-8"))
                    sampling.write_text(json.dumps({
                        "key": [],
                        "frame": {"candidates": {}},
                        "run_manifest_sha256": hashlib.sha256(
                            manifest.read_bytes()
                        ).hexdigest(),
                        "parameter_set": record["method_parameters"]["parameter_set"],
                    }), encoding="utf-8")
                    geo_out = root / f"{name}-geo-eval.json"
                    geo_out.unlink(missing_ok=True)
                    code, stdout, err = _invoke(evaluate_main, [
                        "harborlens-evaluate", "--run", str(run_dir),
                        "--sampling", str(sampling),
                        "--labels", str(labels),
                        "--out", str(geo_out),
                        "--label-provenance", "synthetic",
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(f"candidate GeoJSON '{geo}' is not valid JSON", err)
                    self.assertNotIn("wrong shape", err)
                    self.assertNotIn("not valid UTF-8", err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(geo_out.exists())

    def test_agreement_sampling_long_integer_exits_2(self):
        header = (
            "sample_id,annotator_id,label,confidence,evidence_level,"
            "evidence_sources,fragment_of_longer_stop,duration_judgement,notes\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sheet_a = root / "a.csv"
            sheet_b = root / "b.csv"
            sheet_a.write_text(
                header + "S0001,A1,at_anchor,medium,L2,ais_track,false,assessable,\n",
                encoding="utf-8",
            )
            sheet_b.write_text(
                header + "S0001,A2,at_anchor,medium,L2,ais_track,false,assessable,\n",
                encoding="utf-8",
            )
            sampling = root / "sample.sampling.json"
            sampling.write_text(
                json.dumps({"key": [{"sample_id": "S0001", "kind": "candidate"}]}),
                encoding="utf-8",
            )
            ok = root / "ok.json"
            report = agreement(sheet_a, sheet_b, ok, sampling)
            self.assertEqual(report["units"], 1)
            self.assertTrue(ok.is_file())

            for name, payload in (
                ("integer", '{"x": ' + ("9" * 5000) + "}"),
                ("nested", "[" * 100000 + "]" * 100000),
                ("bytes", None),
            ):
                with self.subTest(kind=name):
                    if payload is None:
                        sampling.write_bytes(b"\xff")
                        expected = "is not valid UTF-8"
                        absent = "not valid JSON"
                    else:
                        sampling.write_text(payload, encoding="utf-8")
                        expected = "is not valid JSON"
                        absent = "not valid UTF-8"
                    out = root / f"{name}.json"
                    code, stdout, err = _invoke(agreement_main, [
                        "harborlens-label-agreement",
                        "--sheets", str(sheet_a), str(sheet_b),
                        "--sampling", str(sampling),
                        "--out", str(out),
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(f"sampling file '{sampling}' {expected}", err)
                    self.assertNotIn(absent, err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())

    def test_agreement_sampling_wrong_shape_is_not_called_invalid_json(self):
        header = (
            "sample_id,annotator_id,label,confidence,evidence_level,"
            "evidence_sources,fragment_of_longer_stop,duration_judgement,notes\n"
        )
        row = "S0001,A1,at_anchor,medium,L2,ais_track,false,assessable,\n"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sheet_a = root / "a.csv"
            sheet_b = root / "b.csv"
            sheet_a.write_text(header + row, encoding="utf-8")
            sheet_b.write_text(
                header + "S0001,A2,at_anchor,medium,L2,ais_track,false,assessable,\n",
                encoding="utf-8",
            )
            sampling = root / "sample.sampling.json"
            valid = {"key": [{"sample_id": "S0001", "kind": "candidate"}]}
            sampling.write_text(json.dumps(valid), encoding="utf-8")
            ok = root / "ok.json"
            code, stdout, err = _invoke(agreement_main, [
                "harborlens-label-agreement",
                "--sheets", str(sheet_a), str(sheet_b),
                "--sampling", str(sampling),
                "--out", str(ok),
            ])
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            self.assertTrue(ok.is_file())
            self.assertEqual(json.loads(ok.read_text(encoding="utf-8"))["units"], 1)

            wrong = (
                ("array", []),
                ("null", None),
                ("key_string", {"key": "no"}),
                ("key_missing", {"other": 1}),
                ("item_int", {"key": [1]}),
                ("missing_kind", {"key": [{"sample_id": "S0001"}]}),
                ("missing_sample_id", {"key": [{"kind": "candidate"}]}),
            )
            for name, payload in wrong:
                with self.subTest(kind=name):
                    sampling.write_text(json.dumps(payload), encoding="utf-8")
                    out = root / f"{name}.json"
                    out.unlink(missing_ok=True)
                    code, stdout, err = _invoke(agreement_main, [
                        "harborlens-label-agreement",
                        "--sheets", str(sheet_a), str(sheet_b),
                        "--sampling", str(sampling),
                        "--out", str(out),
                    ])
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(
                        f"sampling file '{sampling}' is valid JSON but has the wrong shape",
                        err,
                    )
                    self.assertNotIn("is not valid JSON", err)
                    self.assertEqual(err.count("error:"), 1)
                    self.assertNotIn("Traceback", err)
                    self.assertFalse(out.exists())

            sampling.write_text(json.dumps({"key": []}), encoding="utf-8")
            empty_key = root / "empty-key.json"
            code, stdout, err = _invoke(agreement_main, [
                "harborlens-label-agreement",
                "--sheets", str(sheet_a), str(sheet_b),
                "--sampling", str(sampling),
                "--out", str(empty_key),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("does not describe the labeled sample_ids", err)
            self.assertNotIn("is not valid JSON", err)
            self.assertNotIn("wrong shape", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(empty_key.exists())

            sampling.write_text("{bad", encoding="utf-8")
            broken = root / "broken.json"
            code, stdout, err = _invoke(agreement_main, [
                "harborlens-label-agreement",
                "--sheets", str(sheet_a), str(sheet_b),
                "--sampling", str(sampling),
                "--out", str(broken),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn(f"sampling file '{sampling}' is not valid JSON", err)
            self.assertNotIn("wrong shape", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(broken.exists())


class RequestedWindowTests(unittest.TestCase):
    """AIS window rules run before ingest. Federal Register limits do not apply."""

    def test_declared_window_keeps_the_analysis_rules_only(self):
        self.assertIsNone(declared_window())
        ordered = declared_window("2024-01-02T00:00:00Z", "2024-01-02T06:00:00Z")
        self.assertLess(ordered["start"], ordered["end"])
        # A span far past 370 days, a start before 1994, and an end after
        # today are accepted. Those limits belong to harborlens-fr-timeline.
        long_window = declared_window("2022-01-01T00:00:00Z", "2024-01-03T00:00:00Z")
        self.assertLess(long_window["start"], long_window["end"])
        declared_window("1993-12-31T00:00:00Z", "1994-01-02T00:00:00Z")
        declared_window("2024-01-02T00:00:00Z", "2099-01-01T00:00:00Z")
        with self.assertRaisesRegex(AnalysisWindowError, "--window-start must precede --window-end"):
            declared_window("2024-01-02T06:00:00Z", "2024-01-02T00:00:00Z")
        with self.assertRaisesRegex(AnalysisWindowError, "--window-start must precede --window-end"):
            declared_window("2024-01-02T00:00:00Z", "2024-01-02T00:00:00Z")
        with self.assertRaisesRegex(AnalysisWindowError, "Provide both --window-start and --window-end"):
            declared_window("2024-01-02T00:00:00Z", None)
        with self.assertRaisesRegex(AnalysisWindowError, "--window-start must include a UTC offset or Z"):
            declared_window("2024-01-02T00:00:00", "2024-01-02T06:00:00Z")

    def test_cli_refuses_a_reversed_window_before_creating_parents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent = root / "a"
            parent.mkdir()
            (parent / "keep.txt").write_text("stay", encoding="utf-8")
            out = parent / "b" / "c"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
                "--window-start", "2024-01-02T06:00:00Z",
                "--window-end", "2024-01-02T00:00:00Z",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("--window-start must precede --window-end", err)
            self.assertNotIn("publication window", err)
            self.assertEqual(err.count("error:"), 1)
            self.assertNotIn("Traceback", err)
            self.assertFalse((parent / "b").exists())
            self.assertEqual((parent / "keep.txt").read_text(encoding="utf-8"), "stay")

    def test_long_window_still_succeeds_and_writes_the_nested_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent = root / "a"
            parent.mkdir()
            (parent / "keep.txt").write_text("stay", encoding="utf-8")
            out = parent / "b" / "c"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(out),
                "--window-start", "2022-01-01T00:00:00Z",
                "--window-end", "2024-01-03T00:00:00Z",
            ])
            self.assertEqual(code, 0, err)
            self.assertEqual(err, "")
            body = json.loads(stdout)
            self.assertEqual(body["analysis_window"]["status"], "known")
            self.assertEqual(body["analysis_window"]["blocks"][0]["start_utc"], "2022-01-01T00:00:00Z")
            self.assertEqual(body["analysis_window"]["blocks"][0]["end_utc"], "2024-01-03T00:00:00Z")
            self.assertTrue((out / "manifest.json").is_file())
            self.assertEqual((parent / "keep.txt").read_text(encoding="utf-8"), "stay")

    def test_bad_header_does_not_leave_nested_parents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            garbage = root / "garbage.csv"
            garbage.write_text("not,a,valid,ais\n1,2,3,4\n", encoding="utf-8")
            parent = root / "a"
            parent.mkdir()
            (parent / "keep.txt").write_text("stay", encoding="utf-8")
            out = parent / "b" / "c"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(garbage), "--out", str(out),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("missing required column 'mmsi'", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse((parent / "b").exists())
            self.assertEqual((parent / "keep.txt").read_text(encoding="utf-8"), "stay")

    def test_multiday_reversed_window_exits_2_before_reading_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent = root / "a"
            parent.mkdir()
            (parent / "keep.txt").write_text("stay", encoding="utf-8")
            out = parent / "b" / "c"
            missing_a = root / "missing-a.csv"
            missing_b = root / "missing-b.csv"
            code, stdout, err = _invoke(multiday_main, [
                "harborlens-multiday",
                "--input", str(missing_a), str(missing_b),
                "--out", str(out),
                "--window-start", "2024-01-02T00:00:00Z",
                "--window-end", "2023-07-01T00:00:00Z",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("--window-start must precede --window-end", err)
            self.assertNotIn("must exist", err)
            self.assertNotIn("publication window", err)
            self.assertEqual(err.count("error:"), 1)
            self.assertNotIn("Traceback", err)
            self.assertFalse((parent / "b").exists())
            self.assertEqual((parent / "keep.txt").read_text(encoding="utf-8"), "stay")

    def test_sensitivity_accepts_a_multi_year_window_and_rejects_a_reversed_one(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            code, _stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
            ])
            self.assertEqual(code, 0, err)
            cleaned = run_dir / "houston_clean.csv"
            accepted = root / "accepted.json"
            code, stdout, err = _invoke(sensitivity_main, [
                "harborlens-sensitivity",
                "--cleaned", str(cleaned),
                "--out", str(accepted),
                "--window-start", "2022-01-01T00:00:00Z",
                "--window-end", "2024-01-03T00:00:00Z",
            ])
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            self.assertTrue(accepted.is_file())
            report = json.loads(accepted.read_text(encoding="utf-8"))
            self.assertEqual(report["analysis_window"]["start_utc"], "2022-01-01T00:00:00Z")
            self.assertEqual(report["analysis_window"]["end_utc"], "2024-01-03T00:00:00Z")
            self.assertGreaterEqual(report["settings"][0]["stationary_candidates"], 0)

            rejected = root / "rejected.json"
            code, stdout, err = _invoke(sensitivity_main, [
                "harborlens-sensitivity",
                "--cleaned", str(cleaned),
                "--out", str(rejected),
                "--window-start", "2024-01-03T00:00:00Z",
                "--window-end", "2022-01-01T00:00:00Z",
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("--window-start must precede --window-end", err)
            self.assertEqual(err.count("error:"), 1)
            self.assertNotIn("Traceback", err)
            self.assertNotIn("publication window", err)
            self.assertFalse(rejected.exists())


class OutputPathSafetyTests(unittest.TestCase):
    """A failed run does not delete a pre-existing file. A directory symlink is followed."""

    def _bad(self, folder):
        path = Path(folder) / "bad.csv"
        path.write_text("not,a,valid,ais\n1,2,3,4\n", encoding="utf-8")
        return path

    def test_parent_dotdot_does_not_delete_preexisting_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            results = root / "results"
            results.mkdir()
            (results / "notes.txt").write_text("keep-notes", encoding="utf-8")
            (results / "houston_clean.csv").write_text("keep-clean", encoding="utf-8")
            (results / "manifest.json").write_text("keep-manifest", encoding="utf-8")
            bad = self._bad(root)
            previous = os.getcwd()
            try:
                os.chdir(root)
                code, stdout, err = _invoke(harborlens_main, [
                    "harborlens", "--input", str(bad), "--out", "nope/../results",
                ])
                code_dot, stdout_dot, err_dot = _invoke(harborlens_main, [
                    "harborlens", "--input", str(bad), "--out", "nope/..",
                ])
            finally:
                os.chdir(previous)
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertNotIn("Traceback", err)
            self.assertEqual((results / "notes.txt").read_text(encoding="utf-8"), "keep-notes")
            self.assertEqual((results / "houston_clean.csv").read_text(encoding="utf-8"), "keep-clean")
            self.assertEqual((results / "manifest.json").read_text(encoding="utf-8"), "keep-manifest")
            self.assertFalse((root / "nope").exists())
            self.assertEqual(code_dot, 2)
            self.assertEqual(stdout_dot, "")
            self.assertNotIn("Traceback", err_dot)
            self.assertEqual((results / "notes.txt").read_text(encoding="utf-8"), "keep-notes")
            self.assertTrue((root / "bad.csv").is_file())
            self.assertFalse((root / "nope").exists())

    def test_foreign_file_in_a_created_directory_survives(self):
        from harborlens.ais import OutputScope
        original = OutputScope.ensure

        def ensure(self):
            original(self)
            (self.directory / "notes.txt").write_text("foreign", encoding="utf-8")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bad = self._bad(root)
            out = root / "a" / "b" / "c"
            with mock.patch.object(OutputScope, "ensure", ensure):
                code, stdout, err = _invoke(harborlens_main, [
                    "harborlens", "--input", str(bad), "--out", str(out),
                ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertNotIn("Traceback", err)
            self.assertEqual((out / "notes.txt").read_text(encoding="utf-8"), "foreign")
            self.assertFalse((out / "houston_clean.csv").exists())

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory write bits")
    def test_read_only_parent_exits_2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent = root / "locked"
            parent.mkdir()
            parent.chmod(0o555)
            out = parent / "child"
            bad = self._bad(root)
            try:
                code, stdout, err = _invoke(harborlens_main, [
                    "harborlens", "--input", str(bad), "--out", str(out),
                ])
                code_multi, stdout_multi, err_multi = _invoke(multiday_main, [
                    "harborlens-multiday",
                    "--input", str(bad), str(FIXTURE),
                    "--out", str(parent / "multi"),
                ])
            finally:
                parent.chmod(0o700)
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("cannot write output directory", err)
            self.assertIn("Permission denied", err)
            self.assertEqual(err.count("error:"), 1)
            self.assertNotIn("Traceback", err)
            self.assertFalse(out.exists())
            self.assertEqual(code_multi, 2)
            self.assertEqual(stdout_multi, "")
            self.assertIn("cannot write output directory", err_multi)
            self.assertIn("Permission denied", err_multi)
            self.assertNotIn("Traceback", err_multi)
            self.assertFalse((parent / "multi").exists())

    def test_preexisting_directory_symlink_is_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "real"
            target.mkdir()
            (target / "notes.txt").write_text("keep", encoding="utf-8")
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            nested = link / "sub" / "res"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(nested),
            ])
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            self.assertTrue(link.is_symlink())
            self.assertTrue((target / "sub" / "res" / "manifest.json").is_file())
            self.assertEqual((target / "notes.txt").read_text(encoding="utf-8"), "keep")
            direct = link
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(direct),
            ])
            self.assertEqual(code, 0, err)
            self.assertTrue((target / "manifest.json").is_file())
            self.assertEqual((target / "notes.txt").read_text(encoding="utf-8"), "keep")
            self.assertTrue(link.is_symlink())

            bad = self._bad(root)
            failed = link / "child"
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(bad), "--out", str(failed),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertNotIn("Traceback", err)
            self.assertNotIn("symlink", err)
            self.assertEqual((target / "notes.txt").read_text(encoding="utf-8"), "keep")
            self.assertFalse((target / "child").exists())
            self.assertTrue(link.is_symlink())

            dangling = root / "dangling"
            dangling.symlink_to(root / "missing-target")
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(dangling / "out"),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("symlink", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse((root / "missing-target").exists())

            payload = root / "payload.txt"
            payload.write_text("file", encoding="utf-8")
            file_link = root / "file-link"
            file_link.symlink_to(payload)
            code, stdout, err = _invoke(harborlens_main, [
                "harborlens", "--input", str(FIXTURE), "--out", str(file_link),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("not a directory", err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(payload.read_text(encoding="utf-8"), "file")

    def test_swapped_created_directory_is_refused_and_not_removed(self):
        from harborlens.ais import OutputScope
        safe = None
        original = OutputScope.ensure

        def ensure(self):
            original(self)
            moved = self.directory.with_name(self.directory.name + "-moved")
            self.directory.rename(moved)
            self.directory.symlink_to(safe, target_is_directory=True)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            safe = root / "safe"
            safe.mkdir()
            (safe / "notes.txt").write_text("SAFE", encoding="utf-8")
            out = root / "made"
            with mock.patch.object(OutputScope, "ensure", ensure):
                code, stdout, err = _invoke(harborlens_main, [
                    "harborlens", "--input", str(FIXTURE), "--out", str(out),
                ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("symlink", err)
            self.assertEqual(err.count("error:"), 1)
            self.assertNotIn("Traceback", err)
            self.assertEqual((safe / "notes.txt").read_text(encoding="utf-8"), "SAFE")
            self.assertTrue(out.is_symlink())
            self.assertFalse((safe / "houston_clean.csv").exists())

    def test_keyboard_interrupt_during_mkdir_rolls_back(self):
        real_mkdir = os.mkdir

        def mkdir(name, *args, **kwargs):
            if name == "leaf":
                raise KeyboardInterrupt
            return real_mkdir(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            out = root / "a" / "leaf"
            with mock.patch("harborlens.ais.os.mkdir", mkdir):
                with self.assertRaises(KeyboardInterrupt):
                    from harborlens.ais import run
                    run(FIXTURE, out)
            self.assertFalse((root / "a").exists())
            self.assertFalse(out.exists())

    def test_swapped_created_file_is_not_unlinked(self):
        def swap_then_fail(folder, manifest, source_url=None):
            target = Path(folder) / "houston_clean.csv"
            # Rename keeps the original inode allocated so it cannot be reused.
            target.rename(target.with_name("houston_clean.csv.held"))
            target.write_text("SURVIVOR", encoding="utf-8")
            raise RuntimeError("injected")

        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            with mock.patch("harborlens.ais.add_provenance", swap_then_fail):
                with self.assertRaises(RuntimeError):
                    from harborlens.ais import run
                    run(FIXTURE, out)
            self.assertEqual((out / "houston_clean.csv").read_text(encoding="utf-8"), "SURVIVOR")
            self.assertFalse((out / "stationary_candidates.csv").exists())

    def test_symlinked_artifact_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dangling = root / "multi-out"
            dangling.mkdir()
            leaked = root / "leaked.csv"
            (dangling / "houston_clean.csv").symlink_to(leaked)
            day_a = root / "day-a.csv"
            day_b = root / "day-b.csv"
            day_a.write_bytes(FIXTURE.read_bytes())
            day_b.write_bytes(FIXTURE.read_bytes())
            code, stdout, err = _invoke(multiday_main, [
                "harborlens-multiday", "--input", str(day_a), str(day_b),
                "--out", str(dangling),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("symlink", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(leaked.exists())

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory write bits")
    def test_multiday_read_only_output_exits_2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            day_a = root / "day-a.csv"
            day_b = root / "day-b.csv"
            day_a.write_bytes(FIXTURE.read_bytes())
            day_b.write_bytes(FIXTURE.read_bytes())
            out = root / "locked"
            out.mkdir()
            out.chmod(0o500)
            try:
                code, stdout, err = _invoke(multiday_main, [
                    "harborlens-multiday", "--input", str(day_a), str(day_b),
                    "--out", str(out),
                ])
            finally:
                out.chmod(0o700)
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("cannot write output directory", err)
            self.assertIn("Permission denied", err)
            self.assertEqual(err.count("error:"), 1)
            self.assertNotIn("Traceback", err)
            self.assertFalse((out / "houston_clean.csv").exists())


if __name__ == "__main__":
    unittest.main()
