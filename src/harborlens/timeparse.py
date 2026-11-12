"""ASCII calendar and clock parsing that agrees on Python 3.10 and 3.12.

``datetime.fromisoformat`` and ``date.fromisoformat`` accept a wider set of
strings on Python 3.11+ than on 3.10 (extra fraction lengths, a comma
fraction, ``Z``, week dates, and ``YYYYMMDD``). These helpers never call
that parser. Each one matches an explicit ASCII pattern and builds
``datetime`` or ``date`` from the captured fields. An impossible calendar
value, including 29 February in a non-leap year and hour 24, is rejected
by the constructor.

Callers that need a narrower or wider grammar are documented on the
function they expose. Leading or trailing ASCII whitespace is not part of
any pattern here; only the observation parser and ``censoring.parse_utc``
strip it before matching.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

# ``(?![\s\S])`` is the end of the string. ``$`` would still match before a
# trailing newline, and ``fullmatch`` plus that lookahead rejects it.
_CALENDAR_DATE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(?![\s\S])"
)
_FRACTION = r"(?:\.([0-9]{1,6}))?"
_OFFSET = r"(Z|[+-][0-9]{2}:[0-9]{2})"
_OBSERVATION = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"[T ]"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})"
    + _FRACTION
    + r"(?:" + _OFFSET + r")?"
    + r"(?![\s\S])"
)
_EXPLICIT = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"T"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})"
    + _FRACTION
    + _OFFSET
    + r"(?![\s\S])"
)
_EXPLICIT_NAIVE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"T"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})"
    + _FRACTION
    + r"(?![\s\S])"
)
_REVIEW = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"T"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})"
    + _FRACTION
    + r"Z"
    + r"(?![\s\S])"
)
_ASCII_SPACE = " \t\n\r\f\v"


class ExplicitOffsetRequired(ValueError):
    """A clock matched and no ``Z`` or numeric offset was present."""


def _microseconds(fraction):
    if fraction is None:
        return 0
    return int(fraction.ljust(6, "0"))


def _zone(offset):
    """Return a fixed offset. ``None``, ``Z``, ``+00:00`` and ``-00:00`` are UTC."""
    if offset is None or offset == "Z":
        return timezone.utc
    sign, hours, minutes = offset[0], int(offset[1:3]), int(offset[4:6])
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError("Invalid UTC offset")
    delta = timedelta(hours=hours, minutes=minutes)
    if sign == "-":
        delta = -delta
    if delta == timedelta(0):
        return timezone.utc
    return timezone(delta)


def _clock(year, month, day, hour, minute, second, fraction, offset):
    try:
        parsed = datetime(
            int(year), int(month), int(day),
            int(hour), int(minute), int(second),
            _microseconds(fraction),
            tzinfo=_zone(offset),
        )
    except ValueError as exc:
        raise ValueError("Invalid calendar time") from exc
    return parsed.astimezone(timezone.utc)


def parse_calendar_date(value):
    """Return a ``date`` for ASCII ``YYYY-MM-DD`` only.

    ISO week dates (``2024-W01-1``) and basic dates (``20240102``) are
    rejected on Python 3.10 and 3.12. So are a non-ASCII digit, a missing
    zero, surrounding whitespace, and any trailing character. 29 February
    is accepted in a leap year and rejected otherwise. Hour 24 is not a
    date form and does not match.
    """
    if not isinstance(value, str):
        raise ValueError("Date must be YYYY-MM-DD")
    match = _CALENDAR_DATE.fullmatch(value)
    if match is None:
        raise ValueError("Date must be YYYY-MM-DD")
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError("Date must be YYYY-MM-DD") from exc


def parse_observation_time(value):
    """Parse one NOAA-style AIS timestamp and return aware UTC.

    Accepted, after stripping leading and trailing ASCII whitespace:
    ``YYYY-MM-DD``, then one ``T`` or one space, then ``HH:MM:SS``, then
    no fraction or 1 to 6 fractional digits. The offset may be absent
    (naive values are UTC, the NOAA BaseDateTime convention), ``Z``,
    ``+00:00``, ``-00:00``, or another ``±HH:MM``. A non-UTC offset is
    converted to UTC. Seven or more fractional digits, a comma fraction,
    ``+HHMM``, a lowercase ``t`` or ``z``, an arbitrary separator, a time
    with no seconds, a non-ASCII digit, and trailing junk are rejected.
    """
    if not isinstance(value, str):
        raise ValueError("Invalid AIS timestamp")
    match = _OBSERVATION.fullmatch(value.strip(_ASCII_SPACE))
    if match is None:
        raise ValueError("Invalid AIS timestamp")
    year, month, day, hour, minute, second, fraction, offset = match.groups()
    try:
        return _clock(year, month, day, hour, minute, second, fraction, offset)
    except ValueError as exc:
        raise ValueError("Invalid AIS timestamp") from exc


def parse_explicit_utc(value):
    """Parse ``YYYY-MM-DDTHH:MM:SS`` with a required offset. No whitespace strip.

    The separator is uppercase ``T`` only. The offset is ``Z`` or
    ``±HH:MM``, and a non-UTC offset is converted to UTC. The fraction is
    absent or 1 to 6 digits. A missing offset raises
    ``ExplicitOffsetRequired``. A space separator, a lowercase ``t`` or
    ``z``, a comma fraction, seven fractional digits, ``+HHMM``, and
    trailing junk, including a trailing space, are rejected.
    """
    if not isinstance(value, str):
        raise ValueError("Invalid ISO 8601 timestamp")
    match = _EXPLICIT.fullmatch(value)
    if match is None:
        if _EXPLICIT_NAIVE.fullmatch(value) is not None:
            raise ExplicitOffsetRequired("UTC offset or Z required")
        raise ValueError("Invalid ISO 8601 timestamp")
    year, month, day, hour, minute, second, fraction, offset = match.groups()
    try:
        return _clock(year, month, day, hour, minute, second, fraction, offset)
    except ValueError as exc:
        raise ValueError("Invalid ISO 8601 timestamp") from exc


def parse_review_utc(value):
    """Parse a release-review clock. ``Z`` only. No whitespace strip.

    Accepted shape: ASCII ``YYYY-MM-DDTHH:MM:SS``, no fraction or 1 to 6
    fractional digits, then ``Z``. ``+00:00`` and every other offset are
    rejected. A lowercase ``t`` or ``z``, a space, a comma fraction, seven
    or more fractional digits, a non-ASCII digit, a date-only value, and
    trailing junk are rejected. The returned value is aware UTC.
    """
    if not isinstance(value, str):
        raise ValueError("Review timestamp must be an RFC3339 UTC date-time")
    match = _REVIEW.fullmatch(value)
    if match is None:
        raise ValueError("Review timestamp must be an RFC3339 UTC date-time")
    year, month, day, hour, minute, second, fraction = match.groups()
    try:
        return _clock(year, month, day, hour, minute, second, fraction, "Z")
    except ValueError as exc:
        raise ValueError("Invalid review timestamp") from exc
