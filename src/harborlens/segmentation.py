"""Single segmentation engine for unvalidated stationary candidates (SPEC-002, #37).

Both the single-file CLI (``harborlens``) and the multi-day CLI
(``harborlens-multiday``) feed time-ordered observations into ``Segmenter``.
Split rules, discard rules, diagnostics and candidate identity therefore come
from one place; the callers only differ in where group members are stored.

Every result is a ``stationary_candidate`` with ``confidence_label=unvalidated``.
It is NOT a berth, anchorage, wait, port call or navigation signal (BR-001).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields

from harborlens.io_safe import AISInputError
from harborlens.provenance import digests_equal
from harborlens.vessel import AttributeSummary, mmsi_category

METHOD_VERSION = "stationary-v0.2"
KNOTS_TO_MPS = 0.514444
DISCARD_REASONS = ("too_few_points", "too_short", "radius_exceeded")
SPLIT_REASONS = ("timestamp_conflicts", "gap_splits", "identity_conflicts",
                 "implausible_jumps", "spatial_splits")


def haversine_m(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371008.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(x)))


@dataclass(frozen=True)
class SegmentationParams:
    """Research-hypothesis thresholds (BR-003). Defaults reproduce the v0.1 values."""

    max_sog_knots: float = 0.5
    min_duration_minutes: float = 30
    max_gap_minutes: float = 15
    max_radius_m: float = 1000
    min_points: int = 8
    max_jump_knots: float = 65

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise AISInputError(f"Segmentation parameter {item.name} must be a finite number")
        if not (self.max_sog_knots >= 0 and self.min_duration_minutes > 0 and self.max_gap_minutes > 0
                and self.max_radius_m > 0 and self.max_jump_knots > 0):
            raise AISInputError("Segmentation thresholds must be positive (max_sog_knots may be 0)")
        if int(self.min_points) != self.min_points or self.min_points < 2:
            raise AISInputError("min_points must be an integer of at least 2")
        # Canonical types: CLI floats and API ints for the same threshold must yield
        # identical manifests, run IDs and parameter sets.
        for item in fields(self):
            value = getattr(self, item.name)
            object.__setattr__(self, item.name, int(value) if item.name == "min_points" else float(value))

    def values(self):
        return asdict(self)

    @property
    def parameter_set(self):
        """Short, stable fingerprint of the thresholds, carried by every candidate."""
        canonical = json.dumps({k: float(v) for k, v in self.values().items()},
                               sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"{METHOD_VERSION}|{canonical}".encode()).hexdigest()[:12]

    def manifest(self):
        return {"method_version": METHOD_VERSION, **self.values(), "parameter_set": self.parameter_set}

    @classmethod
    def from_manifest(cls, record):
        """Rebuild parameters from a manifest/GeoJSON block and verify its fingerprint."""
        if not isinstance(record, dict) or record.get("method_version") != METHOD_VERSION:
            raise AISInputError("Unsupported or missing candidate method version")
        try:
            params = cls(**{item.name: record[item.name] for item in fields(cls)})
        except KeyError as exc:
            raise AISInputError(f"Candidate method parameters missing {exc}") from exc
        if not digests_equal(record.get("parameter_set"), params.parameter_set):
            raise AISInputError("Candidate parameter_set does not match its parameters")
        return params


def new_diagnostics():
    return {
        "vessels": 0, "points": 0, "moving_points": 0,
        **{reason: 0 for reason in SPLIT_REASONS},
        "discarded_groups": 0,
        "discarded_by_reason": {reason: 0 for reason in DISCARD_REASONS},
        "stationary_candidates": 0,
        "candidates_per_mmsi": {"max": 0, "mmsi_with_multiple": 0},
    }


class Segmenter:
    """Streaming segmentation over observations sorted by (mmsi, time, input order).

    ``store`` keeps group members: ``add(group_id, ref, lon, lat)`` and
    ``points(group_id)`` returning (lon, lat) pairs. ``emit(record, group)``
    receives each accepted candidate. ``censoring`` classifies window edges.
    """

    def __init__(self, params, store, emit, censoring):
        self.params = params
        self.store = store
        self.emit = emit
        self.censoring = censoring
        self.stats = new_diagnostics()
        self.current = None
        self.group_id = 0
        self.last_mmsi = None
        self.last_key = None
        self.mmsi_candidates = 0

    def _close_mmsi(self):
        per = self.stats["candidates_per_mmsi"]
        per["max"] = max(per["max"], self.mmsi_candidates)
        if self.mmsi_candidates > 1:
            per["mmsi_with_multiple"] += 1
        self.mmsi_candidates = 0

    def _discard(self, reason):
        self.stats["discarded_groups"] += 1
        self.stats["discarded_by_reason"][reason] += 1

    def _finish(self):
        group, self.current = self.current, None
        if group is None:
            return
        p = self.params
        if group["count"] < p.min_points:
            return self._discard("too_few_points")
        span = (group["end_dt"] - group["start_dt"]).total_seconds() / 60
        if span < p.min_duration_minutes:
            return self._discard("too_short")
        center = (group["sum_lon"] / group["count"], group["sum_lat"] / group["count"])
        max_distance = max((haversine_m(center, point) for point in self.store.points(group["gid"])),
                           default=0)
        if max_distance > p.max_radius_m:
            return self._discard("radius_exceeded")
        start = group["start_dt"].isoformat().replace("+00:00", "Z")
        end = group["end_dt"].isoformat().replace("+00:00", "Z")
        left, right = self.censoring.classify(group["start_dt"], group["end_dt"])
        record = {
            "event_id": hashlib.sha256(
                f"{group['mmsi']}|{start}|{end}|{METHOD_VERSION}|{p.parameter_set}".encode()
            ).hexdigest()[:18],
            "mmsi": group["mmsi"], "start_utc": start, "end_utc": end,
            "duration_min": round(span, 2), "point_count": group["count"],
            "centroid_lon": round(center[0], 6), "centroid_lat": round(center[1], 6),
            "maximum_distance_m": round(max_distance, 1),
            "type": "stationary_candidate", "method_version": METHOD_VERSION,
            "parameter_set": p.parameter_set, "confidence_label": "unvalidated",
            "left_censoring": left, "right_censoring": right,
            "vessel_type": group["vessel_type"] or "",
            **group["attributes"].result(),
            "mmsi_category": mmsi_category(group["mmsi"]),
        }
        self.stats["stationary_candidates"] += 1
        self.mmsi_candidates += 1
        self.emit(record, group)

    def feed(self, mmsi, when, lat, lon, sog, vessel_type="", ref=None, attributes=None):
        """Consume one observation. Input must be sorted by (mmsi, when, ref)."""
        key = (mmsi, when)
        if self.last_key is not None and key < self.last_key:
            raise AISInputError("Segmenter input is not sorted by MMSI and time")
        self.last_key = key
        self.stats["points"] += 1
        if mmsi != self.last_mmsi:
            self._finish()
            if self.last_mmsi is not None:
                self._close_mmsi()
            self.stats["vessels"] += 1
            self.last_mmsi = mmsi
        p = self.params
        if sog > p.max_sog_knots:
            self.stats["moving_points"] += 1
            self._finish()
            return
        group = self.current
        if group is not None:
            gap = (when - group["end_dt"]).total_seconds() / 60.0
            reason = None
            if gap <= 0:
                reason = "timestamp_conflicts"
            elif gap > p.max_gap_minutes:
                reason = "gap_splits"
            elif group["vessel_type"] and vessel_type and vessel_type != group["vessel_type"]:
                reason = "identity_conflicts"
            elif haversine_m(group["last"], (lon, lat)) / (gap * 60) / KNOTS_TO_MPS > p.max_jump_knots:
                reason = "implausible_jumps"
            elif haversine_m(group["first"], (lon, lat)) > 2 * p.max_radius_m:
                reason = "spatial_splits"
            if reason:
                self.stats[reason] += 1
                self._finish()
        if self.current is None:
            self.group_id += 1
            self.current = {"gid": self.group_id, "mmsi": mmsi, "start_dt": when, "end_dt": when,
                            "first": (lon, lat), "last": (lon, lat), "sum_lat": 0.0, "sum_lon": 0.0,
                            "count": 0, "vessel_type": vessel_type, "attributes": AttributeSummary()}
        group = self.current
        group["end_dt"] = when
        group["last"] = (lon, lat)
        group["sum_lat"] += lat
        group["sum_lon"] += lon
        group["count"] += 1
        if not group["vessel_type"] and vessel_type:
            group["vessel_type"] = vessel_type
        group["attributes"].add(attributes)
        self.store.add(group["gid"], ref, lon, lat)

    def close(self):
        self._finish()
        if self.last_mmsi is not None:
            self._close_mmsi()
        return self.stats


class MemoryStore:
    """In-memory group membership for single-file runs."""

    def __init__(self):
        self.groups = {}

    def add(self, group_id, ref, lon, lat):
        if group_id not in self.groups:
            # Only the current group can grow; drop finished groups to bound memory.
            self.groups = {group_id: []}
        self.groups[group_id].append((lon, lat))

    def points(self, group_id):
        return iter(self.groups.get(group_id, ()))


def geojson_method_member(params):
    """Foreign member placed on candidate FeatureCollections so consumers can read thresholds."""
    return params.manifest()


def add_threshold_arguments(parser):
    """Expose every threshold on a CLI; defaults equal SegmentationParams()."""
    defaults = SegmentationParams()
    group = parser.add_argument_group("segmentation thresholds (research hypotheses, BR-003)")
    group.add_argument("--max-sog-knots", type=float, default=defaults.max_sog_knots)
    group.add_argument("--min-duration-minutes", type=float, default=defaults.min_duration_minutes)
    group.add_argument("--max-gap-minutes", type=float, default=defaults.max_gap_minutes)
    group.add_argument("--max-radius-m", type=float, default=defaults.max_radius_m)
    group.add_argument("--min-points", type=int, default=defaults.min_points)
    group.add_argument("--max-jump-knots", type=float, default=defaults.max_jump_knots)


def params_from_args(args):
    return SegmentationParams(
        max_sog_knots=args.max_sog_knots, min_duration_minutes=args.min_duration_minutes,
        max_gap_minutes=args.max_gap_minutes, max_radius_m=args.max_radius_m,
        min_points=args.min_points, max_jump_knots=args.max_jump_knots,
    )
