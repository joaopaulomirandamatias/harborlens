"""CLI exit codes, help text and --version for the research commands.

Expected domain errors exit 2 through argparse, with no traceback unless
--debug is set. --debug still exits 2. A bug still propagates. KeyboardInterrupt
is not caught. Synthetic fixtures only.
"""
import contextlib
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
from harborlens.evaluation import _read_labels, main as evaluate_main
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
