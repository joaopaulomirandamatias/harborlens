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
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harborlens import __version__
from harborlens.ais import REQUIRED_COLUMNS, header_alias
from harborlens.cli import main as harborlens_main
from harborlens.evaluation import _read_labels, evaluate, main as evaluate_main
from harborlens.labeling import draw_sample
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


if __name__ == "__main__":
    unittest.main()
