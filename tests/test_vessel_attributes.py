"""Vessel attributes and MMSI QA flags (SPEC-001, issue #39). Synthetic AIS only."""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from harborlens.ais import CLEAN_FIELDS, load_cleaned, read_candidates_csv, run
from harborlens.multiday import run_multiday
from harborlens.vessel import mmsi_category, normalize_attributes

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"
# Column layout of the 2024 NOAA daily archives (lowercase, transceiver last).
NOAA_2024 = ["mmsi", "base_date_time", "longitude", "latitude", "sog", "cog", "heading", "vessel_name",
             "imo", "call_sign", "vessel_type", "status", "length", "width", "draft", "cargo", "transceiver"]
DAY = datetime(2024, 1, 2)


def stop_rows(mmsi, start, minutes, length="180", draft="9.5", tclass="A", heading="45", cog="12.5"):
    return [[mmsi, (start + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"), -95.0, 29.5, 0.1, cog,
             heading, "SYNTHETIC", "", "", "70", "1", length, "30", draft, "", tclass]
            for i in range(0, minutes + 1, 5)]


def write(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(NOAA_2024)
        writer.writerows(rows)
    return path


class MmsiCategoryTests(unittest.TestCase):
    def test_itu_prefixes(self):
        cases = {
            # MID 199 is outside 201-775 and mmsi_category returns other (leading digit 1).
            # MID 200 is also outside that block and still uses a ship prefix.
            "199012345": "other", "199090001": "other", "200000001": "ship",
            "003669999": "coast_station",
            "036612345": "group_of_ships", "111366123": "sar_aircraft", "970123456": "ais_sart",
            "972123456": "mob_device", "974123456": "epirb_ais", "982661234": "craft_associated_with_parent_ship",
            "993661234": "aid_to_navigation", "836612345": "handheld_vhf", "000000000": "placeholder",
            "111111111": "placeholder", "123456789": "placeholder", "36612345": "leading_zero_ambiguous",
            "912345678": "other",
        }
        for mmsi, expected in cases.items():
            with self.subTest(mmsi=mmsi):
                self.assertEqual(mmsi_category(mmsi), expected)

    def test_sentinels_become_missing(self):
        clean = normalize_attributes(cog="360", heading="511", length="0", width="0", draft="0", transceiver="")
        self.assertTrue(all(value is None for value in clean.values()))
        good = normalize_attributes(cog="359.9", heading="0", length="294.1", width="32", draft="12.4",
                                    transceiver="Class B")
        self.assertEqual(good, {"cog_deg": 359.9, "heading_deg": 0.0, "length_m": 294.1, "width_m": 32.0,
                                "draft_m": 12.4, "transceiver_class": "B"})
        self.assertIsNone(normalize_attributes(cog="nan", transceiver="X")["cog_deg"])
        self.assertIsNone(normalize_attributes(transceiver="X")["transceiver_class"])


class AttributePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        start = DAY + timedelta(hours=23)
        rows = (stop_rows("199000101", start, 120)
                + stop_rows("993661234", start, 120, length="0", draft="0", tclass="", heading="511", cog="360"))
        self.whole = write(self.root / "whole.csv", rows)
        self.day1 = write(self.root / "d1.csv", [r for r in rows if r[1] < "2024-01-03"])
        self.day2 = write(self.root / "d2.csv", [r for r in rows if r[1] >= "2024-01-03"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_noaa_2024_header_cleaned_with_attributes_and_categories(self):
        manifest = run(self.whole, self.root / "out")
        self.assertEqual(manifest["mmsi_categories"], {"aid_to_navigation": 25, "other": 25})
        with (self.root / "out" / "houston_clean.csv").open(newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, CLEAN_FIELDS)
            rows = list(reader)
        ship = next(r for r in rows if r["mmsi"] == "199000101")
        aton = next(r for r in rows if r["mmsi"] == "993661234")
        self.assertEqual((ship["length_m"], ship["draft_m"], ship["transceiver_class"]), ("180.0", "9.5", "A"))
        self.assertEqual((aton["heading_deg"], aton["cog_deg"], aton["length_m"]), ("", "", ""))
        validator = Draft202012Validator(json.loads((SCHEMAS / "ais-point.schema.json").read_text()),
                                         format_checker=FormatChecker())
        numeric = {"lat", "lon", "sog_knots", "cog_deg", "heading_deg", "length_m", "width_m", "draft_m"}
        for row in rows:
            validator.validate({k: (float(v) if k in numeric and v != "" else v) for k, v in row.items()})

    def test_non_ship_identifiers_are_flagged_not_dropped(self):
        run(self.whole, self.root / "out")
        records = {r["mmsi"]: r for r in read_candidates_csv(self.root / "out" / "stationary_candidates.csv")}
        self.assertEqual(records["993661234"]["mmsi_category"], "aid_to_navigation")
        self.assertIsNone(records["993661234"]["length_m"])
        self.assertIsNone(records["993661234"]["transceiver_class"])
        self.assertEqual((records["199000101"]["length_m"], records["199000101"]["draft_m"],
                          records["199000101"]["transceiver_class"]), (180.0, 9.5, "A"))

    def test_candidate_attributes_match_across_pipelines(self):
        run(self.whole, self.root / "single")
        manifest = run_multiday([self.day1, self.day2], self.root / "multi")
        single = read_candidates_csv(self.root / "single" / "stationary_candidates.csv")
        multi = read_candidates_csv(self.root / "multi" / "stationary_candidates.csv")
        self.assertEqual(single, multi)
        self.assertEqual(manifest["mmsi_categories"], {"aid_to_navigation": 25, "other": 25})
        feature_schema = Draft202012Validator(
            json.loads((SCHEMAS / "multi-day-candidate-feature.schema.json").read_text()))
        for feature in json.loads((self.root / "multi" / "stationary_candidates.geojson").read_text())["features"]:
            feature_schema.validate(feature)

    def test_older_cleaned_files_without_attribute_columns_still_load(self):
        legacy = self.root / "legacy.csv"
        with legacy.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["mmsi", "timestamp_utc", "lat", "lon", "sog_knots", "vessel_type", "nav_status"])
            writer.writerow(["199000101", "2024-01-02T00:00:00Z", 29.5, -95.0, 0.1, "70", "1"])
        rows, unparsable = load_cleaned(legacy)
        self.assertEqual(unparsable, 0)
        self.assertIsNone(rows[0][7]["length_m"])


class ShipCategoryAboveAllocatedMidTests(unittest.TestCase):
    """A leading digit 7 above the allocated MID block stays ``ship``.

    ITU-R M.585 assigns a ship station identity as three maritime
    identification digits (MID) plus six figures. The ITU Table of Maritime
    Identification Digits (ITU MARS, GLAD) is published at
    https://www.itu.int/en/ITU-R/terrestrial/fmd/Pages/mid.aspx and
    https://www.itu.int/gladapp/Allocation/MIDs . The U.S. Coast Guard
    Navigation Center summarizes that table: MIDs are three-digit identifiers
    ranging from 201 to 775 (https://www.navcen.uscg.gov/mmsi-formats).
    MID 790 is above 775, so it is not an allocated MID. ``mmsi_category``
    in ``src/harborlens/vessel.py`` still returns ``ship`` when the first
    digit is ``7``.
    """

    MMSI = "790000001"

    def test_classifier_marks_an_unallocated_leading_seven_as_ship(self):
        self.assertEqual(mmsi_category(self.MMSI), "ship")
        self.assertFalse(201 <= int(self.MMSI[:3]) <= 775)

    def test_pipeline_writes_ship_for_an_unallocated_leading_seven(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write(root / "ship.csv", stop_rows(self.MMSI, DAY, 40))
            manifest = run(source, root / "out")
            self.assertEqual(manifest["mmsi_categories"], {"ship": 9})
            with (root / "out" / "houston_clean.csv").open(newline="") as handle:
                cleaned = list(csv.DictReader(handle))
            self.assertTrue(cleaned)
            self.assertTrue(all(
                row["mmsi"] == self.MMSI and row["mmsi_category"] == "ship" for row in cleaned
            ))
            records = read_candidates_csv(root / "out" / "stationary_candidates.csv")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["mmsi"], self.MMSI)
            self.assertEqual(records[0]["mmsi_category"], "ship")


if __name__ == "__main__":
    unittest.main()
