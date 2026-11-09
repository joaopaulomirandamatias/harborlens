"""Regression of literal 2024 Federal anchorage coordinates; NO AIS claims."""
import json
import tempfile
import unittest
from pathlib import Path

from harborlens.cfr_anchorages import (
    BOUNDARIES, RegulatoryGeometryError, inspect_regulated_areas, parse_dms, save_audit,
)

class RegulatoryAnchorageTests(unittest.TestCase):
    def test_four_areas_from_2024_cfr(self):
        report=inspect_regulated_areas("2024-07-01")
        self.assertEqual(set(BOUNDARIES),{"A","B","C","A_EAST"})
        self.assertEqual(len(report["areas"]),4)
        self.assertEqual(report["source_edition_date"],"2024-07-01")
        self.assertEqual(report["source_regulatory_date_validity"],"as_of_2024_07_01_only")
        self.assertTrue(all(x["source_reference"]=="33 CFR 110.197(a)" for x in report["areas"]))

    def test_precise_dms_conversion_and_lon_sign(self):
        north = "29°20'48.5" + chr(34) + "N"
        west = "94°42'54.0" + chr(34) + "W"
        self.assertAlmostEqual(parse_dms(north, "lat"), 29+20/60+48.5/3600, 9)
        self.assertAlmostEqual(parse_dms(west, "lon"), -(94+42/60+54/3600), 9)

    def test_source_datum_not_invented_for_a_b_c(self):
        report=inspect_regulated_areas()
        for area in report["areas"]:
            if area["id"]=="A_EAST":
                self.assertEqual(area["source_datum"],"NAD83_explicit")
            else:
                self.assertEqual(area["source_datum"],"not_explicitly_specified")
                self.assertIn("horizontal_datum_requires_independent_resolution",area["review_blockers"])
            self.assertFalse(area["ais_spatial_join_permitted"])
            self.assertFalse(area["verified_anchorage_or_waiting"])

    def test_topology_a_east_not_silently_fixed(self):
        report=inspect_regulated_areas()
        statuses={a["id"]:a["literal_ring_topology"] for a in report["areas"]}
        self.assertEqual(statuses["A_EAST"],"invalid_literal_ring")
        self.assertTrue(all(statuses[x]=="valid_literal_ring" for x in ("A","B","C")))
        flagged=next(x for x in report["areas"] if x["id"]=="A_EAST")
        self.assertIn("published_vertex_sequence_requires_expert_review",flagged["review_blockers"])

    def test_2024_january_not_automatically_covered(self):
        report=inspect_regulated_areas("2024-01-02")
        self.assertEqual(report["evidence_date_scope"],"prior_to_available_annual_edition_unverified")
        self.assertTrue(all("historical_date_not_established_by_2024_07_01_edition" in a["review_blockers"] for a in report["areas"]))

    def test_reject_naive_invalid_dms(self):
        q = chr(34)
        invalid = ("94°99'00.0"+q+"W", "94°59'60.0"+q+"W",
                   "999°01'01"+q+"W", "94°01'00"+q+"N", "unknown")
        for token in invalid:
            with self.subTest(value=token):
                with self.assertRaises(RegulatoryGeometryError):
                    parse_dms(token, "lon")
        with self.assertRaises(RegulatoryGeometryError):
            inspect_regulated_areas("2024-02-30")

    def test_source_coordinate_order_preserved_and_closed(self):
        report=inspect_regulated_areas()
        for area in report["areas"]:
            self.assertEqual(len(area["source_lat_lon_dms"]),4)
            self.assertEqual(len(area["transcribed_lon_lat_in_source_datum"]),4)
            self.assertTrue(area["ring_closed"])
            self.assertEqual(area["source_lat_lon_dms"][0]["latitude"],BOUNDARIES[area["id"]][0][0])

    def test_output_is_json_not_implied_wgs84_geojson(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/"2024-cfr-anchorage-audit.json"
            result=save_audit(out,"2024-07-01")
            record=json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(record["areas"],result["areas"])
            self.assertNotIn("features",record)
            self.assertIn("NOT WGS84 GeoJSON",record["warning"])
            with self.assertRaisesRegex(RegulatoryGeometryError,"overwrite"):
                save_audit(out,"2024-07-01")

    def test_no_automatic_post_2024_temporal_certification(self):
        result=inspect_regulated_areas("2026-11-09")
        self.assertTrue(all(not a["ais_spatial_join_permitted"] for a in result["areas"]))
        self.assertEqual(result["source_regulatory_date_validity"],"as_of_2024_07_01_only")

if __name__=="__main__":
    unittest.main()
