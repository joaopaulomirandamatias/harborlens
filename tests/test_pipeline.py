import csv
import tempfile
import unittest
from pathlib import Path
from harborlens.ais import haversine_m, infer_candidates, ingest, run

FIXTURE=Path(__file__).parent/"fixtures"/"synthetic_ais.csv"
class HarborLensTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.work=Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def test_haversine(self):
        self.assertLess(haversine_m((-95,29),(-95,29)),0.01)
        self.assertGreater(haversine_m((-95,29),(-95,30)),100000)
    def test_synthetic_data(self):
        result=run(FIXTURE,self.work/"out")
        self.assertEqual(result["counts"],{"total":63,"in_bbox":61,"missing_value":0,"invalid":1,"outside_bbox":1,"duplicate":1,"written":60})
        self.assertEqual(result["events"]["stationary_candidates"],1)
        with (self.work/"out"/"stationary_candidates.csv").open() as f:
            event=list(csv.DictReader(f))[0]
        self.assertEqual(event["confidence_label"],"unvalidated")
        self.assertEqual(float(event["duration_min"]),45.0)
    def test_gaps(self):
        cleaned=self.work/"clean.csv"
        ingest(FIXTURE,cleaned)
        events,_=infer_candidates(cleaned,max_gap_minutes=5)
        self.assertEqual(len(events),1)

if __name__=="__main__":
    unittest.main()
