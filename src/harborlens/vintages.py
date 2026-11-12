"""NOAA Marine Cadastre daily AIS archive vintages (SPEC-001, issue #36).

Each supported year maps to one archive layout: download URL template,
compression and expected header style. Years outside the registry are refused
instead of guessing a URL. The ``verification`` field states how the layout was
established; it is engineering evidence, not a rights or completeness review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from harborlens.io_safe import AISInputError

LEGACY_HEADER = ("MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName", "IMO",
                 "CallSign", "VesselType", "Status", "Length", "Width", "Draft", "Cargo", "TransceiverClass")
CSV2_HEADER = ("mmsi", "base_date_time", "longitude", "latitude", "sog", "cog", "heading", "vessel_name",
               "imo", "call_sign", "vessel_type", "status", "length", "width", "draft", "cargo", "transceiver")


@dataclass(frozen=True)
class Vintage:
    layout: str
    url_template: str
    filename_template: str
    compression: str
    header_style: str
    missing_values: str
    verification: str

    def filename(self, day):
        return self.filename_template.format(year=day.year, month=day.month, day=day.day, date=day.isoformat())

    def url(self, day):
        return self.url_template.format(year=day.year, filename=self.filename(day))


ZIP_DAILY = Vintage(
    layout="marinecadastre_zip_daily_v1",
    url_template="https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/{filename}",
    filename_template="AIS_{year}_{month:02d}_{day:02d}.zip",
    compression="zip", header_style="legacy_camel_case", missing_values="sentinels",
    verification=("URL pattern documented for 2022 daily files and the 2023 directory index; "
                  "not downloaded by this project"),
)
CSV2_ZST = Vintage(
    layout="marinecadastre_csv2_zst_v1",
    url_template="https://noaaocm.blob.core.windows.net/ais/csv2/csv{year}/{filename}",
    filename_template="ais-{date}.csv.zst",
    compression="zst", header_style="lowercase_snake_case", missing_values="nulls",
    verification=("2024 archives downloaded and hashed in source-pinned project runs; "
                  "2025-2026 follow the published csv2 index pattern, not yet downloaded"),
)
REGISTRY = {**{year: ZIP_DAILY for year in range(2015, 2024)}, **{year: CSV2_ZST for year in (2024, 2025, 2026)}}


def vintage_for(day):
    """Vintage for a UTC calendar day; refuses unregistered years (2009-2014 use other schemas)."""
    if not isinstance(day, date):
        raise AISInputError("A calendar date is required")
    vintage = REGISTRY.get(day.year)
    if vintage is None:
        raise AISInputError(f"No verified NOAA daily archive layout registered for {day.year}")
    return vintage


def header_style(header):
    """Classify a CSV header as one of the known NOAA styles, or 'unrecognized'."""
    names = {name.strip() for name in header}
    if {"MMSI", "BaseDateTime", "LAT", "LON"} <= names:
        return "legacy_camel_case"
    if {"mmsi", "base_date_time", "latitude", "longitude"} <= names:
        return "lowercase_snake_case"
    return "unrecognized"
