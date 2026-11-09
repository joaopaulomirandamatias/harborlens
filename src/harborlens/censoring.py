"""Analysis-window censoring flags for stationary candidates (SPEC-002, BR-019).

A candidate observed inside a bounded extraction window may have started before
the window opened or continued after it closed. Its reported duration is then
only a lower bound. This module records the analysis window, flags candidates
whose first or last observation lies within one ``max_gap_minutes`` of a window
edge, and fails closed when the declared window contradicts the observations.

Censoring flags describe observation coverage only. They do not turn a
stationary candidate into a berth, anchorage, wait or port call.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harborlens.io_safe import AISInputError

RULE_VERSION = "window-edge-v1"
CENSORED = "censored"
NOT_CENSORED = "not_censored"
UNKNOWN = "unknown"
MAX_SIDECAR_BYTES = 1024 * 1024


class AnalysisWindowError(AISInputError):
    """The declared analysis window is missing, malformed or contradicts the data."""


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value, name="time") -> datetime:
    """Parse an ISO 8601 instant that carries an explicit UTC offset or Z."""
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnalysisWindowError(f"Invalid ISO 8601 {name}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise AnalysisWindowError(f"{name} must include a UTC offset or Z")
    return parsed.astimezone(timezone.utc)


def _window(start, end, source, **extra):
    a, b = parse_utc(start, "window start"), parse_utc(end, "window end")
    if not a < b:
        raise AnalysisWindowError("Analysis window start must precede its end")
    return {"start": a, "end": b, "source": source, **extra}


def declared_window(start=None, end=None):
    """Return a user-declared window, or None when neither bound is given."""
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise AnalysisWindowError("Provide both --window-start and --window-end")
    return _window(start, end, "user_declared")


def sidecar_path(path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".source.json")


def sidecar_window(path, input_sha256):
    """Read the window from a HarborLens acquisition sidecar next to ``path``.

    Supported sidecars: ``harborlens-extract-noaa-archive`` and
    ``harborlens-fetch-erddap``. The sidecar must describe exactly these input
    bytes; a hash mismatch is an error rather than a silent fallback.
    Returns None when no recognised sidecar exists.
    """
    path = Path(path)
    side = sidecar_path(path)
    if not side.is_file():
        return None
    if side.stat().st_size > MAX_SIDECAR_BYTES:
        raise AnalysisWindowError(f"Acquisition sidecar is too large: {side.name}")
    try:
        record = json.loads(side.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise AnalysisWindowError(f"Acquisition sidecar is not valid JSON: {side.name}") from exc
    if not isinstance(record, dict):
        return None
    if record.get("source_type") == "local_noaa_daily_archive":
        keys, source = ("window_start_utc", "window_end_utc", "output_sha256"), "extraction_sidecar"
    elif record.get("dataset") == "AIS2024_AIS":
        keys, source = ("time_start_utc", "time_end_utc", "csv_sha256"), "erddap_sidecar"
    else:
        return None
    if record.get(keys[2]) != input_sha256:
        raise AnalysisWindowError(
            f"Acquisition sidecar {side.name} does not match the input bytes; "
            "remove it or pass --window-start/--window-end explicitly"
        )
    return _window(record.get(keys[0]), record.get(keys[1]), source,
                   sidecar_sha256=hashlib.sha256(side.read_bytes()).hexdigest())


def resolve_input_window(path, input_sha256, start=None, end=None):
    """Combine an explicit declaration with a verified sidecar, failing on conflict."""
    explicit = declared_window(start, end)
    side = sidecar_window(path, input_sha256)
    if explicit and side and (explicit["start"], explicit["end"]) != (side["start"], side["end"]):
        raise AnalysisWindowError("Declared analysis window conflicts with the acquisition sidecar")
    return side or explicit


class WindowCensoring:
    """Classify candidates against contiguous analysis-window blocks.

    Windows separated by no more than ``tolerance_minutes`` are merged, because
    the segmentation rule can bridge such a gap. Larger gaps between windows are
    reported as internal gaps; candidates next to them are censored.
    """

    def __init__(self, windows, tolerance_minutes, declarations=None):
        if tolerance_minutes <= 0:
            raise AnalysisWindowError("Censoring tolerance must be positive")
        self.tolerance = timedelta(minutes=tolerance_minutes)
        self.tolerance_minutes = tolerance_minutes
        self.declarations = declarations or []
        self.blocks = None
        self.internal_gaps = 0
        self.counts = {"left_censored": 0, "right_censored": 0, "both_censored": 0,
                       "uncensored": 0, "unknown": 0}
        if windows:
            ordered = sorted(windows, key=lambda w: (w["start"], w["end"]))
            blocks = [[ordered[0]["start"], ordered[0]["end"]]]
            for item in ordered[1:]:
                if item["start"] - blocks[-1][1] <= self.tolerance:
                    blocks[-1][1] = max(blocks[-1][1], item["end"])
                else:
                    blocks.append([item["start"], item["end"]])
            self.blocks = [tuple(b) for b in blocks]
            self.internal_gaps = len(self.blocks) - 1

    @property
    def known(self):
        return self.blocks is not None

    def check_observed(self, first, last):
        """Fail closed when observations fall outside the declared window span."""
        if not self.known or first is None:
            return
        if first < self.blocks[0][0] or last > self.blocks[-1][1]:
            raise AnalysisWindowError(
                "Observations fall outside the declared analysis window "
                f"({_iso(first)} .. {_iso(last)})"
            )

    def classify(self, start, end):
        """Return (left_censoring, right_censoring) and update run counters."""
        if not self.known:
            self.counts["unknown"] += 1
            return UNKNOWN, UNKNOWN
        for block_start, block_end in self.blocks:
            if block_start <= start and end <= block_end:
                left = CENSORED if start - block_start <= self.tolerance else NOT_CENSORED
                right = CENSORED if block_end - end <= self.tolerance else NOT_CENSORED
                break
        else:
            raise AnalysisWindowError(
                f"Candidate {_iso(start)} .. {_iso(end)} is not inside one declared window block"
            )
        if left == CENSORED:
            self.counts["left_censored"] += 1
        if right == CENSORED:
            self.counts["right_censored"] += 1
        if left == CENSORED and right == CENSORED:
            self.counts["both_censored"] += 1
        if left == NOT_CENSORED and right == NOT_CENSORED:
            self.counts["uncensored"] += 1
        return left, right

    def summary(self, observed=None):
        result = {
            "status": "known" if self.known else "unknown",
            "rule_version": RULE_VERSION,
            "edge_tolerance_minutes": self.tolerance_minutes,
            "blocks": [{"start_utc": _iso(a), "end_utc": _iso(b)} for a, b in (self.blocks or [])],
            "internal_gaps": self.internal_gaps,
            "declarations": self.declarations,
        }
        if observed is not None:
            result["observed_time_range"] = observed
        return result

    def run_id_component(self):
        """Window blocks that change outputs; None keeps legacy run IDs stable."""
        return [[_iso(a), _iso(b)] for a, b in self.blocks] if self.known else None

    def event_summary(self):
        return {"rule_version": RULE_VERSION, **self.counts}


def declaration_record(input_name, window):
    """Serializable record of how one input's window was established."""
    if window is None:
        return {"input": input_name, "source": "none"}
    record = {"input": input_name, "source": window["source"],
              "start_utc": _iso(window["start"]), "end_utc": _iso(window["end"])}
    if "sidecar_sha256" in window:
        record["sidecar_sha256"] = window["sidecar_sha256"]
    return record


def observed_range(first, last):
    return {"start_utc": _iso(first) if first else None, "end_utc": _iso(last) if last else None}
