"""Offline Federal Register part 110 index-contract tests."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock
from urllib.error import URLError

from harborlens.fr_timeline import (
    EARLIEST_PUBLICATION, FederalRegisterAuditError, _date, _today, initial_url,
    main, scan_part110, save_scan, validate_publication_window,
)

class Response(io.BytesIO):
    def __init__(self, value):
        raw = json.dumps(value).encode("utf-8")
        super().__init__(raw)
        self.headers = {"Content-Length": str(len(raw))}

def doc(number, published="2023-08-11"):
    return {
        "document_number": number, "title": "Synthetic Part 110 change",
        "publication_date": published, "effective_on": published,
        "type": "Rule", "html_url": "https://www.federalregister.gov/documents/synthetic",
        "cfr_references": [{"title": 33, "part": 110}],
        "abstract": "Synthetic only. No real legal conclusion.",
    }

class FederalRegisterTests(unittest.TestCase):
    def test_query_fixed_host_and_cfr_bounds(self):
        u = initial_url("2023-07-01", "2024-01-02")
        self.assertIn("www.federalregister.gov/api/v1/documents.json", u)
        self.assertIn("conditions%5Bcfr%5D%5Bpart%5D=110", u)
        self.assertIn("2024-01-02", u)

    def test_two_pages_all_docs_require_review(self):
        first = initial_url("2023-07-01", "2024-01-02", per_page=2)
        second = initial_url("2023-07-01", "2024-01-02", per_page=2) + "&page=2"
        def fetch(request,timeout):
            return Response({"count":3,"results":[doc("A"),doc("B")],
                             "next_page_url":second} if request.full_url == first
                            else {"count":3,"results":[doc("C")],"next_page_url":None})
        report = scan_part110(opener=fetch,per_page=2)
        self.assertEqual(report["count"],3)
        self.assertEqual(len(report["query_pages"]),2)
        self.assertTrue(report["index_pagination_complete"])
        self.assertEqual(report["cfr_section_110_197_effective_state"],"NOT_DETERMINED")
        self.assertFalse(report["intervening_amendments_excluded"])
        self.assertFalse(report["ais_spatial_join_permitted"])
        self.assertTrue(all(x["review_status"].startswith("requires_manual") for x in report["documents"]))

    def test_no_results_is_not_legal_clearance(self):
        result = scan_part110(opener=lambda req,timeout: Response({
            "count":0,"results":[],"next_page_url":None
        }))
        self.assertEqual(result["count"],0)
        self.assertIn("not proof",result["no_result_interpretation"])

    def test_fail_closed_on_missing_page(self):
        with self.assertRaisesRegex(FederalRegisterAuditError,"Incomplete paginated"):
            scan_part110(opener=lambda req,timeout: Response({"count":2,"results":[doc("A")]}))

    def test_reject_external_pagination_url(self):
        with self.assertRaisesRegex(FederalRegisterAuditError,"fixed official"):
            scan_part110(opener=lambda req,timeout: Response({
                "count":2,"results":[doc("A")],
                "next_page_url":"https://malicious.example/api/v1/documents.json"
            }))

    def test_reject_same_host_pagination_that_drops_scope(self):
        url = "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bcfr%5D%5Btitle%5D=40&conditions%5Bcfr%5D%5Bpart%5D=52&conditions%5Bpublication_date%5D%5Bgte%5D=2023-07-01&conditions%5Bpublication_date%5D%5Blte%5D=2024-01-02"
        with self.assertRaisesRegex(FederalRegisterAuditError, "Part 110 scope"):
            scan_part110(opener=lambda req, timeout: Response({
                "count":2, "results":[doc("A")], "next_page_url":url
            }))

    def test_reject_duplicate_document_numbers(self):
        with self.assertRaisesRegex(FederalRegisterAuditError,"Repeated"):
            scan_part110(opener=lambda req,timeout: Response({
                "count":2,"results":[doc("A"),doc("A")],
            }))

    def test_reject_out_of_range_publication_date(self):
        with self.assertRaisesRegex(FederalRegisterAuditError,"outside requested"):
            scan_part110(opener=lambda req,timeout: Response({
                "count":1,"results":[doc("A","2025-06-01")]
            }))

    def test_reject_excessive_window_and_invalid_dates(self):
        with self.assertRaises(FederalRegisterAuditError):
            initial_url("2022-01-01","2024-01-02")
        with self.assertRaises(FederalRegisterAuditError):
            initial_url("2024-01-02","2023-07-01")
        with self.assertRaises(FederalRegisterAuditError):
            initial_url("2024-02-30","2024-03-01")

    def test_response_size_and_format_guards(self):
        def bad(request,timeout):
            value=Response({"count":0,"results":[]})
            value.headers["Content-Length"]="999999999"
            return value
        with self.assertRaisesRegex(FederalRegisterAuditError,"byte limit"):
            scan_part110(opener=bad)
        with self.assertRaises(FederalRegisterAuditError):
            scan_part110(opener=lambda req,timeout: io.BytesIO(b"not JSON"))

    def test_file_persistence_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"fr.json"
            result=save_scan(path,opener=lambda req,timeout: Response({
                "count":1,"results":[doc("A")],
            }))
            self.assertEqual(result["count"],1)
            self.assertEqual(json.loads(path.read_text())["count"],1)
            with self.assertRaisesRegex(FederalRegisterAuditError,"new"):
                save_scan(path,opener=lambda req,timeout: Response({"count":0,"results":[]}))


# Calendar text that _date rejects. Each flag is tested on its own.
_INVALID_DATES = (
    "2026-W10-1",
    "20260301",
    "٢٠٢٦-٠٣-٠١",
    "2026-02-30",
)


def _forbid_network(*_args, **_kwargs):
    raise AssertionError("network client was called")


# Tests freeze the publication clock on this UTC day.
FROZEN_TODAY = date(2026, 11, 21)
_USAGE = "usage: harborlens-fr-timeline [-h] [-V] [--start START] [--end END] --out OUT [--debug]"
_OLD_WINDOW_SENTENCE = "Use a historical publication window of at most 370 days"
_START_AFTER_END = (
    "--start (2024-01-02) is after --end (2023-07-01). "
    "Use calendar dates YYYY-MM-DD, with start on or before end, "
    "a span of at most 370 days, start in 1994 or later, and end not after today."
)
_BEFORE_1994 = (
    "--start (1993-12-31) is before 1994-01-01, the earliest date this command accepts."
)
_END_AFTER_TODAY = (
    "--end (2026-11-22) is after today (2026-11-21). "
    "Use a historical end date on or before today."
)
_SPAN_371 = (
    "--start and --end span 371 days; the maximum historical publication window is 370 days."
)


class FederalRegisterCliDateTests(unittest.TestCase):
    """Invalid --start/--end exit 2 before urlopen. Valid dates scan as before."""

    def _run(self, argv, urlopen):
        stderr = io.StringIO()
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
                mock.patch("harborlens.fr_timeline.urlopen", urlopen), \
                contextlib.redirect_stderr(stderr), \
                contextlib.redirect_stdout(stdout):
            main()
        return stdout.getvalue(), stderr.getvalue()

    def test_invalid_start_and_end_exit_2_with_no_network(self):
        for flag in ("--start", "--end"):
            other = "--end" if flag == "--start" else "--start"
            valid = "2024-01-02" if flag == "--start" else "2023-07-01"
            for text in _INVALID_DATES:
                with self.subTest(flag=flag, text=text):
                    with self.assertRaises(FederalRegisterAuditError) as raised:
                        _date(text)
                    message = str(raised.exception)
                    self.assertTrue(message)
                    with tempfile.TemporaryDirectory() as folder:
                        out = Path(folder) / "fr.json"
                        client = mock.Mock(side_effect=_forbid_network)
                        stderr = io.StringIO()
                        with mock.patch.object(sys, "argv", [
                            "harborlens-fr-timeline", flag, text, other, valid, "--out", str(out),
                        ]), mock.patch("harborlens.fr_timeline.urlopen", client), \
                                contextlib.redirect_stderr(stderr):
                            with self.assertRaises(SystemExit) as caught:
                                main()
                        self.assertEqual(caught.exception.code, 2)
                        text_err = stderr.getvalue()
                        self.assertIn(message, text_err)
                        self.assertIn(f"error: {message}", text_err)
                        self.assertNotIn("Traceback", text_err)
                        self.assertEqual(client.call_count, 0)
                        self.assertFalse(out.exists())
                        self.assertFalse(out.with_name(out.name + ".partial").exists())

    def test_start_after_end_stays_a_window_error(self):
        """A real calendar start after end exits 2 with that rule's message.

        stderr is the argparse usage line plus one error line. stdout is
        empty. No traceback, no output file, and urlopen is not called.
        The frozen clock is 2026-11-21.
        """
        start, end = "2024-01-02", "2023-07-01"
        self.assertEqual((date(2026, 1, 7) - date(2025, 1, 1)).days, 371)
        with self.assertRaises(FederalRegisterAuditError) as direct:
            validate_publication_window(start, end, today=FROZEN_TODAY)
        self.assertEqual(str(direct.exception), _START_AFTER_END)
        self.assertNotIn(_OLD_WINDOW_SENTENCE, str(direct.exception))
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "fr.json"
            client = mock.Mock(side_effect=_forbid_network)
            request = mock.Mock(side_effect=_forbid_network)
            stderr = io.StringIO()
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", [
                "harborlens-fr-timeline", "--start", start, "--end", end,
                "--out", str(out),
            ]), mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline.Request", request), \
                    mock.patch("harborlens.fr_timeline._today", return_value=FROZEN_TODAY), \
                    mock.patch.dict("os.environ", {"COLUMNS": "120"}), \
                    contextlib.redirect_stderr(stderr), \
                    contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as caught:
                    main()
            self.assertEqual(caught.exception.code, 2)
            text_err = stderr.getvalue()
            self.assertEqual(
                text_err,
                _USAGE + "\n" + f"harborlens-fr-timeline: error: {_START_AFTER_END}\n",
            )
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn("Traceback", text_err)
            self.assertNotIn(_OLD_WINDOW_SENTENCE, text_err)
            self.assertEqual(client.call_count, 0)
            self.assertEqual(request.call_count, 0)
            self.assertFalse(out.exists())
            self.assertFalse(out.with_name(out.name + ".partial").exists())

    def test_keyboard_interrupt_and_bare_value_error_propagate(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "fr.json"
            argv = [
                "harborlens-fr-timeline", "--start", "2023-07-01",
                "--end", "2024-01-02", "--out", str(out),
            ]
            client = mock.Mock(side_effect=_forbid_network)
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline._date", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    main()
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline._date", side_effect=ValueError("bare")):
                with self.assertRaises(ValueError) as caught:
                    main()
            self.assertEqual(str(caught.exception), "bare")
            self.assertEqual(client.call_count, 0)
            self.assertFalse(out.exists())

    def test_valid_dates_follow_the_existing_scan_path(self):
        payload = {"count": 1, "results": [doc("SYN-1")], "next_page_url": None}

        def fake(request, timeout):
            self.assertEqual(timeout, 45)
            self.assertIn("www.federalregister.gov", request.full_url)
            return Response(payload)

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch("harborlens.fr_timeline._today", return_value=FROZEN_TODAY):
            root = Path(folder)
            direct = save_scan(root / "direct.json", "2023-07-01", "2024-01-02", opener=fake)
            out = root / "cli.json"
            client = mock.Mock(side_effect=fake)
            stdout, stderr = self._run(
                [
                    "harborlens-fr-timeline", "--start", "2023-07-01",
                    "--end", "2024-01-02", "--out", str(out),
                ],
                client,
            )
            self.assertEqual(stderr, "")
            self.assertEqual(client.call_count, 1)
            self.assertNotIn("Traceback", stderr)
            report = json.loads(out.read_text(encoding="utf-8"))
            report.pop("retrieved_at_utc")
            direct.pop("retrieved_at_utc")
            self.assertEqual(report, direct)
            summary = json.loads(stdout)
            self.assertEqual(summary, {
                "documents_for_review": 1,
                "query_pages": 1,
                "section_110_197_legal_state": "NOT_DETERMINED",
                "ais_spatial_join_permitted": False,
            })


class FederalRegisterWindowRuleTests(unittest.TestCase):
    """Each window rule exits 2 with its own message and no network call."""

    def setUp(self):
        self.assertEqual(EARLIEST_PUBLICATION, date(1994, 1, 1))
        self.assertEqual(FROZEN_TODAY, date(2026, 11, 21))
        self.assertEqual((date(2026, 1, 7) - date(2025, 1, 1)).days, 371)
        self.assertEqual((date(2026, 1, 6) - date(2025, 1, 1)).days, 370)

    def _violations(self):
        return (
            ("start_after_end", "2024-01-02", "2023-07-01", _START_AFTER_END),
            ("start_before_1994", "1993-12-31", "1994-01-02", _BEFORE_1994),
            ("end_after_today", "2026-11-01", "2026-11-22", _END_AFTER_TODAY),
            ("span_over_370", "2025-01-01", "2026-01-07", _SPAN_371),
        )

    def _boundaries(self):
        return (
            ("span_370", "2025-01-01", "2026-01-06"),
            ("start_equals_end", "2024-01-02", "2024-01-02"),
            ("end_equals_today", "2026-11-01", "2026-11-21"),
            ("start_equals_1994", "1994-01-01", "1994-01-02"),
        )

    def _run_cli(self, start, end, urlopen, today, request=None):
        stderr = io.StringIO()
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "fr.json"
            argv = [
                "harborlens-fr-timeline", "--start", start, "--end", end,
                "--out", str(out),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch("harborlens.fr_timeline.urlopen", urlopen), \
                    mock.patch("harborlens.fr_timeline._today", return_value=today), \
                    mock.patch.dict("os.environ", {"COLUMNS": "120"}), \
                    contextlib.redirect_stderr(stderr), \
                    contextlib.redirect_stdout(stdout):
                request_patch = (
                    mock.patch("harborlens.fr_timeline.Request", request)
                    if request is not None else contextlib.nullcontext()
                )
                with request_patch:
                    try:
                        main()
                    except SystemExit as caught:
                        code = caught.code
                    else:
                        code = None
            written = out.exists() or out.with_name(out.name + ".partial").exists()
        return code, stderr.getvalue(), stdout.getvalue(), written

    def test_each_rule_exits_2_with_its_message_and_no_network(self):
        for name, start, end, message in self._violations():
            with self.subTest(rule=name):
                client = mock.Mock(side_effect=_forbid_network)
                request = mock.Mock(side_effect=_forbid_network)
                with mock.patch("harborlens.fr_timeline.urlopen", client), \
                        mock.patch("harborlens.fr_timeline.Request", request):
                    with self.assertRaises(FederalRegisterAuditError) as direct:
                        initial_url(start, end, today=FROZEN_TODAY)
                    with self.assertRaises(FederalRegisterAuditError) as checked:
                        validate_publication_window(start, end, today=FROZEN_TODAY)
                self.assertEqual(str(direct.exception), message)
                self.assertEqual(str(checked.exception), message)
                self.assertEqual(client.call_count, 0)
                self.assertEqual(request.call_count, 0)

                client = mock.Mock(side_effect=_forbid_network)
                request = mock.Mock(side_effect=_forbid_network)
                code, stderr, stdout, written = self._run_cli(
                    start, end, client, FROZEN_TODAY, request,
                )
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertEqual(
                    stderr,
                    _USAGE + "\n" + f"harborlens-fr-timeline: error: {message}\n",
                )
                self.assertNotIn("Traceback", stderr)
                self.assertNotIn(_OLD_WINDOW_SENTENCE, stderr)
                self.assertEqual(stderr.count(message), 1)
                self.assertEqual(client.call_count, 0)
                self.assertEqual(request.call_count, 0)
                self.assertFalse(written)

    def test_boundary_windows_pass_validation(self):
        for name, start, end in self._boundaries():
            with self.subTest(boundary=name):
                client = mock.Mock(side_effect=_forbid_network)
                request = mock.Mock(side_effect=_forbid_network)
                with mock.patch("harborlens.fr_timeline.urlopen", client), \
                        mock.patch("harborlens.fr_timeline.Request", request):
                    parsed = validate_publication_window(start, end, today=FROZEN_TODAY)
                    url = initial_url(start, end, today=FROZEN_TODAY)
                self.assertEqual(parsed, (date.fromisoformat(start), date.fromisoformat(end)))
                self.assertIn("www.federalregister.gov/api/v1/documents.json", url)
                self.assertIn(start, url)
                self.assertIn(end, url)
                self.assertEqual(client.call_count, 0)
                self.assertEqual(request.call_count, 0)

                payload = {
                    "count": 1,
                    "results": [doc("SYN-1", start)],
                    "next_page_url": None,
                }

                def fake(request, timeout, body=payload):
                    self.assertEqual(timeout, 45)
                    self.assertIn("www.federalregister.gov", request.full_url)
                    return Response(body)

                client = mock.Mock(side_effect=fake)
                code, stderr, stdout, written = self._run_cli(
                    start, end, client, FROZEN_TODAY,
                )
                self.assertIsNone(code)
                self.assertEqual(stderr, "")
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(client.call_count, 1)
                self.assertTrue(written)
                summary = json.loads(stdout)
                self.assertEqual(summary["documents_for_review"], 1)
                self.assertFalse(summary["ais_spatial_join_permitted"])

    def test_invalid_window_does_not_create_nested_parents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "keep.txt").write_text("stay", encoding="utf-8")
            out = root / "a" / "b" / "fr.json"
            client = mock.Mock(side_effect=_forbid_network)
            request = mock.Mock(side_effect=_forbid_network)
            with mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline.Request", request):
                with self.assertRaises(FederalRegisterAuditError) as caught:
                    save_scan(out, "2024-01-02", "2023-07-01")
            self.assertEqual(str(caught.exception), _START_AFTER_END)
            self.assertEqual(client.call_count, 0)
            self.assertEqual(request.call_count, 0)
            self.assertFalse((root / "a").exists())
            self.assertEqual((root / "keep.txt").read_text(encoding="utf-8"), "stay")

            stderr = io.StringIO()
            stdout = io.StringIO()
            argv = [
                "harborlens-fr-timeline", "--start", "2024-01-02",
                "--end", "2023-07-01", "--out", str(out),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline.Request", request), \
                    mock.patch("harborlens.fr_timeline._today", return_value=FROZEN_TODAY), \
                    contextlib.redirect_stderr(stderr), \
                    contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as caught_exit:
                    main()
            self.assertEqual(caught_exit.exception.code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(_START_AFTER_END, stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertEqual(client.call_count, 0)
            self.assertEqual(request.call_count, 0)
            self.assertFalse((root / "a").exists())
            self.assertFalse(out.exists())

    def test_clock_interrupt_and_bare_value_error_propagate(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "fr.json"
            argv = [
                "harborlens-fr-timeline", "--start", "2024-01-02",
                "--end", "2024-01-02", "--out", str(out),
            ]
            client = mock.Mock(side_effect=_forbid_network)
            request = mock.Mock(side_effect=_forbid_network)
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline.Request", request), \
                    mock.patch("harborlens.fr_timeline._today", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    main()
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline.Request", request), \
                    mock.patch("harborlens.fr_timeline._today", side_effect=ValueError("bare")):
                with self.assertRaises(ValueError) as caught:
                    main()
            self.assertIs(type(caught.exception), ValueError)
            self.assertEqual(str(caught.exception), "bare")
            self.assertEqual(client.call_count, 0)
            self.assertEqual(request.call_count, 0)
            self.assertFalse(out.exists())

    def test_first_true_rule_wins(self):
        # Start is also before 1994. Rule 1 wins.
        with self.assertRaises(FederalRegisterAuditError) as start_after_end:
            validate_publication_window("1993-06-01", "1993-01-01", today=FROZEN_TODAY)
        self.assertIn("is after --end (1993-01-01)", str(start_after_end.exception))
        # End is also after today and the span exceeds 370 days. Rule 2 wins.
        with self.assertRaises(FederalRegisterAuditError) as before_1994:
            validate_publication_window("1993-01-01", "2026-11-22", today=FROZEN_TODAY)
        self.assertEqual(
            str(before_1994.exception),
            "--start (1993-01-01) is before 1994-01-01, the earliest date this command accepts.",
        )

    def test_today_is_utc_and_does_not_call_date_today(self):
        import inspect
        from harborlens import fr_timeline
        self.assertNotIn("date.today(", inspect.getsource(fr_timeline))
        sentinel = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
        with mock.patch("harborlens.fr_timeline.datetime") as clock:
            clock.now.return_value = sentinel
            self.assertEqual(_today(), date(2026, 11, 21))
            clock.now.assert_called_once_with(timezone.utc)

    def test_existing_output_exits_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "fr.json"
            out.write_text("keep\n", encoding="utf-8")
            client = mock.Mock(side_effect=_forbid_network)
            stderr = io.StringIO()
            stdout = io.StringIO()
            argv = [
                "harborlens-fr-timeline", "--start", "2023-07-01",
                "--end", "2024-01-02", "--out", str(out),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline._today", return_value=FROZEN_TODAY), \
                    mock.patch.dict("os.environ", {"COLUMNS": "120"}), \
                    contextlib.redirect_stderr(stderr), \
                    contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as caught:
                    main()
            text_err = stderr.getvalue()
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                text_err,
                _USAGE + "\n" + "harborlens-fr-timeline: error: Output must be a new .json file\n",
            )
            self.assertNotIn("Traceback", text_err)
            self.assertEqual(out.read_text(encoding="utf-8"), "keep\n")
            self.assertEqual(client.call_count, 0)
            self.assertFalse(out.with_name(out.name + ".partial").exists())

    def test_download_failure_exits_2_without_traceback(self):
        client = mock.Mock(side_effect=URLError("timed out"))
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "fr.json"
            stderr = io.StringIO()
            stdout = io.StringIO()
            argv = [
                "harborlens-fr-timeline", "--start", "2023-07-01",
                "--end", "2024-01-02", "--out", str(out),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch("harborlens.fr_timeline.urlopen", client), \
                    mock.patch("harborlens.fr_timeline._today", return_value=FROZEN_TODAY), \
                    mock.patch.dict("os.environ", {"COLUMNS": "120"}), \
                    contextlib.redirect_stderr(stderr), \
                    contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as caught:
                    main()
            text_err = stderr.getvalue()
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                text_err,
                _USAGE + "\n" + "harborlens-fr-timeline: error: Federal Register download failed\n",
            )
            self.assertNotIn("Traceback", text_err)
            self.assertNotIn("timed out", text_err)
            self.assertEqual(client.call_count, 1)
            self.assertFalse(out.exists())
            self.assertFalse(out.with_name(out.name + ".partial").exists())


if __name__ == "__main__":
    unittest.main()
