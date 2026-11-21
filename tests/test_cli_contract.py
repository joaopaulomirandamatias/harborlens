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
from harborlens.cli import main as harborlens_main
from harborlens.evaluation import _read_labels, evaluate, main as evaluate_main
from harborlens.labeling import candidate_feature_collection, draw_sample, sample_main
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
            self.assertIn(f"sampling file '{sampling}' is not valid JSON", err)
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
            with self.assertRaisesRegex(AISInputError, "is not valid JSON"):
                evaluate(run_dir, sampling_path, labels, root / "geo-utf8.json",
                         label_provenance="synthetic")
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
        cases = ("ftp://x", "", "http://", "https://user:secret@example.org")
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


if __name__ == "__main__":
    unittest.main()
