"""Timestamp and calendar grammars are the same on Python 3.10 and 3.12.

Synthetic values only. These tests do not branch on ``sys.version_info``.
A string accepted here is accepted on both interpreters because the parser
builds ``datetime`` and ``date`` from ASCII fields and does not call
``fromisoformat``.
"""
from __future__ import annotations

import contextlib
import inspect
import io
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

import harborlens.ais as ais
import harborlens.archive_extract as archive_extract
import harborlens.censoring as censoring
import harborlens.download as download
import harborlens.erddap as erddap
import harborlens.fr_timeline as fr_timeline
import harborlens.publication as publication
import harborlens.timeparse as timeparse
import harborlens.vintage as vintage
from harborlens.censoring import AnalysisWindowError, parse_utc
from harborlens.erddap import AcquisitionError
from harborlens.fr_timeline import FederalRegisterAuditError
from harborlens.io_safe import AISInputError
from harborlens.publication import ReleaseDenied, _review_moment
from harborlens.timeparse import (
    parse_calendar_date, parse_explicit_utc, parse_observation_time, parse_review_utc,
)
from harborlens.vintage import VintageAuditError

UTC = timezone.utc


def _instant(year, month, day, hour, minute, second, micro):
    return datetime(year, month, day, hour, minute, second, micro, tzinfo=UTC)


def _fraction_suffix(digits):
    if digits == 0:
        return ""
    return "." + ("1" * digits)


class ParserSourceTests(unittest.TestCase):
    def test_call_sites_do_not_call_the_stdlib_iso_parser(self):
        functions = (
            timeparse.parse_calendar_date,
            timeparse.parse_observation_time,
            timeparse.parse_explicit_utc,
            timeparse.parse_review_utc,
            timeparse._clock,
            publication._review_moment,
            ais.parse_time,
            censoring.parse_utc,
            erddap.utc,
            archive_extract.utc,
            vintage._aware_time,
            download._day,
            fr_timeline._date,
        )
        for function in functions:
            with self.subTest(function=function.__qualname__):
                self.assertNotIn("fromisoformat", inspect.getsource(function))


class ObservationGrammarTests(unittest.TestCase):
    """``ais.parse_time``: NOAA naive clocks, ``T`` or one space, optional offset."""

    def test_zero_through_six_fraction_digits_match(self):
        for digits in range(0, 7):
            suffix = _fraction_suffix(digits)
            micro = int(suffix[1:].ljust(6, "0")) if digits else 0
            expected = _instant(2024, 1, 2, 3, 4, 5, micro)
            for text in (
                f"2024-01-02T03:04:05{suffix}",
                f"2024-01-02 03:04:05{suffix}",
                f"2024-01-02T03:04:05{suffix}Z",
                f"2024-01-02T03:04:05{suffix}+00:00",
                f"  2024-01-02T03:04:05{suffix}Z\n",
            ):
                with self.subTest(text=text):
                    self.assertEqual(ais.parse_time(text), expected)

    def test_leap_day_and_non_utc_offset(self):
        self.assertEqual(
            ais.parse_time("2024-02-29T00:00:00Z"),
            _instant(2024, 2, 29, 0, 0, 0, 0),
        )
        self.assertEqual(
            ais.parse_time("2000-02-29T12:00:00"),
            _instant(2000, 2, 29, 12, 0, 0, 0),
        )
        self.assertEqual(
            ais.parse_time("2024-01-02T00:30:00+01:00"),
            _instant(2024, 1, 1, 23, 30, 0, 0),
        )
        self.assertEqual(
            ais.parse_time("2024-01-02T00:00:00-05:00"),
            _instant(2024, 1, 2, 5, 0, 0, 0),
        )
        self.assertEqual(ais.parse_time("2024-01-02T00:00:00-00:00"), ais.parse_time("2024-01-02T00:00:00Z"))

    def test_rejected_shapes_are_value_errors(self):
        rejected = (
            "2024-01-02T00:00:00.1234567Z",
            "2024-01-02T00:00:00,123456Z",
            "2024-01-02T00:00:00+0000",
            "2024-01-02T00:00:00z",
            "2024-01-02t00:00:00Z",
            "2024-01-02x00:00:00Z",
            "2024-01-02T00:00Z",
            "2024-01-02T24:00:00Z",
            "2023-02-29T00:00:00Z",
            "1900-02-29T00:00:00",
            "2024-01-02T00:00:00Z trailing",
            "2024-W01-1T00:00:00Z",
            "20240102T000000Z",
            "2024-01-02T00:00:60Z",
            "2024-01-02T00:60:00Z",
            "2024-01-02T00:00:00+24:00",
            "2024-01-02T00:00:00+00:60",
            "2024-01-02T00:00:00+00:00:00",
            "２０２４-01-02T00:00:00Z",
            "2024-01-0２T00:00:00Z",
            "",
            None,
            20240102,
        )
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ais.parse_time(value)
                with self.assertRaises(ValueError):
                    parse_observation_time(value if isinstance(value, str) else value)

    def test_seven_digits_are_not_truncated_to_six(self):
        with self.assertRaises(ValueError):
            ais.parse_time("2024-01-02T00:00:00.1234567Z")
        self.assertEqual(
            ais.parse_time("2024-01-02T00:00:00.123456Z").microsecond,
            123456,
        )


class ExplicitUtcGrammarTests(unittest.TestCase):
    """Window, ERDDAP, archive, and vintage clocks require ``T`` and an offset."""

    def _accept(self, text):
        expected_parsers = (
            parse_explicit_utc,
            parse_utc,
            erddap.utc,
            archive_extract.utc,
            vintage._aware_time,
        )
        first = parse_explicit_utc(text)
        for parser in expected_parsers:
            with self.subTest(parser=parser.__qualname__, text=text):
                self.assertEqual(parser(text), first)
        return first

    def test_zero_through_six_fraction_digits_and_z_or_zero_offset(self):
        for digits in range(0, 7):
            suffix = _fraction_suffix(digits)
            micro = int(suffix[1:].ljust(6, "0")) if digits else 0
            expected = _instant(2024, 6, 10, 1, 2, 3, micro)
            for text in (
                f"2024-06-10T01:02:03{suffix}Z",
                f"2024-06-10T01:02:03{suffix}+00:00",
            ):
                with self.subTest(text=text):
                    self.assertEqual(self._accept(text), expected)

    def test_leap_day_and_non_utc_offset_convert(self):
        self.assertEqual(self._accept("2024-02-29T23:59:59Z"), _instant(2024, 2, 29, 23, 59, 59, 0))
        self.assertEqual(
            self._accept("2024-01-02T00:30:00+01:00"),
            _instant(2024, 1, 1, 23, 30, 0, 0),
        )
        self.assertEqual(
            self._accept("2024-01-02T00:00:00-05:00"),
            _instant(2024, 1, 2, 5, 0, 0, 0),
        )

    def test_naive_clock_is_rejected_and_only_parse_utc_strips_ascii_space(self):
        for parser, error in (
            (erddap.utc, AcquisitionError),
            (archive_extract.utc, AISInputError),
            (vintage._aware_time, VintageAuditError),
            (parse_utc, AnalysisWindowError),
        ):
            with self.subTest(parser=parser.__qualname__):
                with self.assertRaises(error):
                    parser("2024-01-02T00:00:00")
                with self.assertRaises(error):
                    parser("2024-01-02 00:00:00Z")
        for parser, error in (
            (erddap.utc, AcquisitionError),
            (archive_extract.utc, AISInputError),
            (vintage._aware_time, VintageAuditError),
        ):
            with self.subTest(parser=parser.__qualname__, trailing="space"):
                with self.assertRaises(error):
                    parser("2024-01-02T00:00:00Z ")
        self.assertEqual(parse_utc("  2024-01-02T00:00:00Z\t"), _instant(2024, 1, 2, 0, 0, 0, 0))
        self.assertEqual(parse_utc("2024-01-02T00:00:00Z "), _instant(2024, 1, 2, 0, 0, 0, 0))
        with self.assertRaises(AcquisitionError):
            erddap.utc("  2024-01-02T00:00:00Z")
        with self.assertRaises(AISInputError):
            archive_extract.utc("  2024-01-02T00:00:00Z")
        with self.assertRaises(VintageAuditError):
            vintage._aware_time("  2024-01-02T00:00:00Z")

    def test_shared_rejections(self):
        rejected = (
            "2024-01-02T00:00:00.1234567Z",
            "2024-01-02T00:00:00,1Z",
            "2024-01-02T00:00:00+0000",
            "2024-01-02T00:00:00z",
            "2024-01-02t00:00:00Z",
            "2024-01-02T24:00:00Z",
            "2023-02-29T00:00:00Z",
            "2024-01-02T00:00:00Zjunk",
            "2024-W01-1",
            "20240102",
            "２０２４-01-02T00:00:00Z",
            "2024-01-02T00:00:00+00:00:00",
            "2024-01-02T00:00Z",
            None,
        )
        for value in rejected:
            for parser, error in (
                (parse_explicit_utc, ValueError),
                (parse_utc, AnalysisWindowError),
                (erddap.utc, AcquisitionError),
                (archive_extract.utc, AISInputError),
                (vintage._aware_time, VintageAuditError),
            ):
                with self.subTest(parser=parser.__qualname__, value=value):
                    with self.assertRaises(error):
                        parser(value)


class ReviewClockGrammarTests(unittest.TestCase):
    """Release reviews accept ``Z`` only. ``+00:00`` stays denied."""

    def test_zero_through_six_fraction_digits(self):
        for digits in range(0, 7):
            suffix = _fraction_suffix(digits)
            micro = int(suffix[1:].ljust(6, "0")) if digits else 0
            text = f"2026-11-12T15:00:00{suffix}Z"
            with self.subTest(text=text):
                self.assertEqual(_review_moment(text), _instant(2026, 11, 12, 15, 0, 0, micro))
                self.assertEqual(parse_review_utc(text), _instant(2026, 11, 12, 15, 0, 0, micro))

    def test_leap_day_is_a_real_utc_instant(self):
        self.assertEqual(_review_moment("2024-02-29T00:00:00.1Z").microsecond, 100000)

    def test_plus_zero_and_other_offsets_are_denied(self):
        denied = (
            "2026-11-12T15:00:00+00:00",
            "2026-11-12T15:00:00-00:00",
            "2026-11-12T15:00:00+01:00",
            "2026-11-12T15:00:00-05:00",
            "2026-11-12",
            "2026-11-12Z",
            "2026-11-12T15:00:00",
            "2026-11-12T15:00:00.1234567Z",
            "2026-11-12T15:00:00,1Z",
            "2026-11-12t15:00:00Z",
            "2026-11-12T15:00:00z",
            "2026-11-12 15:00:00Z",
            "2026-11-12T24:00:00Z",
            "2023-02-29T00:00:00Z",
            "2026-11-12T15:00:00Z ",
            "２０２６-11-12T15:00:00Z",
            "2024-W01-1T00:00:00Z",
            None,
        )
        for value in denied:
            with self.subTest(value=value):
                with self.assertRaises(ReleaseDenied):
                    _review_moment(value)


class CalendarDateGrammarTests(unittest.TestCase):
    """``download --date`` and ``fr_timeline._date`` accept ``YYYY-MM-DD`` only."""

    def test_leap_day_and_ordinary_days(self):
        for text, expected in (
            ("2024-02-29", date(2024, 2, 29)),
            ("2000-02-29", date(2000, 2, 29)),
            ("2024-01-02", date(2024, 1, 2)),
            ("1994-01-01", date(1994, 1, 1)),
        ):
            with self.subTest(text=text):
                self.assertEqual(parse_calendar_date(text), expected)
                self.assertEqual(download._day(text), expected)
                self.assertEqual(fr_timeline._date(text), expected)

    def test_week_dates_basic_dates_and_impossible_days_are_rejected(self):
        rejected = (
            "2024-W01-1",
            "2024-W01-01",
            "20240102",
            "2024-02-30",
            "2023-02-29",
            "1900-02-29",
            "2024-1-02",
            "2024-01-2",
            "2024-01-02 ",
            "2024-01-02T00:00:00Z",
            "２０２４-01-02",
            "2024-01-0２",
            "",
            None,
        )
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_calendar_date(value)
                with self.assertRaises(AISInputError):
                    download._day(value)
                with self.assertRaises(FederalRegisterAuditError):
                    fr_timeline._date(value)

    def test_download_cli_exits_2_before_any_network_use(self):
        with tempfile.TemporaryDirectory() as folder:
            for text in ("2024-W01-1", "20240102", "2024-02-30", "2023-02-29", "2024-01-02 "):
                stderr = io.StringIO()
                with self.subTest(text=text), \
                        mock.patch.object(sys, "argv", ["dl", "--date", text, "--directory", folder]), \
                        mock.patch("harborlens.download.urlopen", side_effect=AssertionError("network")), \
                        contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as caught:
                        download.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("YYYY-MM-DD", stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_federal_register_window_rejects_a_week_date(self):
        with self.assertRaises(FederalRegisterAuditError):
            fr_timeline.initial_url("2024-W01-1", "2024-01-08")
        with self.assertRaises(FederalRegisterAuditError):
            fr_timeline.initial_url("20240102", "2024-01-08")


if __name__ == "__main__":
    unittest.main()
