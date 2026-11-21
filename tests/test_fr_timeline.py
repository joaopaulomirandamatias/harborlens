"""Offline Federal Register part 110 index-contract tests."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from harborlens.fr_timeline import (
    EARLIEST_PUBLICATION, MSG_END_AFTER_TODAY, MSG_START_AFTER_END,
    MSG_START_BEFORE_1994, MSG_WINDOW_SPAN, FederalRegisterAuditError, _date,
    initial_url, main, scan_part110, save_scan, validate_window,
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

        with tempfile.TemporaryDirectory() as folder:
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


# Frozen clock for window rules. 2024-06-02 is after this day and before the
# real date.today() in this repository's era, so an "end after today" failure
# is the frozen clock and not the wall clock.
FROZEN_TODAY = date(2024, 6, 1)
_USAGE = "usage: harborlens-fr-timeline [-h] [--start START] [--end END] --out OUT"
_START_AFTER_END = "Start date must be on or before the end date"
_END_AFTER_TODAY = "End date must be on or before today"
_START_BEFORE_1994 = "Start date must be on or after 1994-01-01"
_WINDOW_SPAN = "Use a historical publication window of at most 370 days"


class FederalRegisterWindowRuleTests(unittest.TestCase):
    """Each window rule exits 2 with its own message and no network call."""

    def setUp(self):
        self.assertEqual(MSG_START_AFTER_END, _START_AFTER_END)
        self.assertEqual(MSG_END_AFTER_TODAY, _END_AFTER_TODAY)
        self.assertEqual(MSG_START_BEFORE_1994, _START_BEFORE_1994)
        self.assertEqual(MSG_WINDOW_SPAN, _WINDOW_SPAN)
        self.assertEqual(EARLIEST_PUBLICATION, date(1994, 1, 1))
        self.assertLess(date(2024, 6, 2), date.today())

    def _violations(self):
        span_start = date(2023, 1, 1)
        span_end = span_start + timedelta(days=371)
        self.assertEqual((span_end - span_start).days, 371)
        self.assertLess(span_end, FROZEN_TODAY)
        return (
            ("start_after_end", "2024-01-02", "2023-07-01", _START_AFTER_END),
            ("end_after_today", "2024-06-01", "2024-06-02", _END_AFTER_TODAY),
            ("start_before_1994", "1993-12-31", "1994-01-01", _START_BEFORE_1994),
            ("span_over_370", span_start.isoformat(), span_end.isoformat(), _WINDOW_SPAN),
        )

    def _boundaries(self):
        span_start = date(2023, 1, 1)
        span_end = span_start + timedelta(days=370)
        self.assertEqual((span_end - span_start).days, 370)
        self.assertLess(span_end, FROZEN_TODAY)
        return (
            ("span_370", span_start.isoformat(), span_end.isoformat()),
            ("start_equals_end", "2024-01-02", "2024-01-02"),
            ("end_equals_today", "2024-05-01", FROZEN_TODAY.isoformat()),
            ("start_equals_1994", "1994-01-01", "1994-01-01"),
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
                        validate_window(start, end, today=FROZEN_TODAY)
                self.assertEqual(str(direct.exception), message)
                self.assertEqual(str(checked.exception), message)
                self.assertEqual(client.call_count, 0)
                self.assertEqual(request.call_count, 0)

                client = mock.Mock(side_effect=_forbid_network)
                request = mock.Mock(side_effect=_forbid_network)
                code, stderr, _stdout, written = self._run_cli(
                    start, end, client, FROZEN_TODAY, request,
                )
                self.assertEqual(code, 2)
                self.assertEqual(
                    stderr,
                    _USAGE + "\n" + f"harborlens-fr-timeline: error: {message}\n",
                )
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(stderr.count(message), 1)
                if message != _WINDOW_SPAN:
                    self.assertNotIn("370", stderr)
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
                    parsed = validate_window(start, end, today=FROZEN_TODAY)
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


if __name__ == "__main__":
    unittest.main()
