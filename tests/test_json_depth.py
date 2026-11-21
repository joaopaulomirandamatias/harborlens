"""Boundary tests for the shared JSON container-depth counter."""
import json
import tempfile
import unittest
from pathlib import Path

from harborlens.censoring import AnalysisWindowError, sidecar_window
from harborlens.json_depth import MAX_JSON_NESTING, max_container_depth


class JsonDepthTests(unittest.TestCase):
    def test_limit_is_accepted_and_one_deeper_is_rejected(self):
        self.assertEqual(MAX_JSON_NESTING, 512)
        at_limit = "[" * MAX_JSON_NESTING + "1" + "]" * MAX_JSON_NESTING
        over_limit = "[" * (MAX_JSON_NESTING + 1) + "1" + "]" * (MAX_JSON_NESTING + 1)
        self.assertEqual(max_container_depth(at_limit), MAX_JSON_NESTING)
        self.assertEqual(max_container_depth(over_limit), MAX_JSON_NESTING + 1)
        self.assertLessEqual(
            max_container_depth(at_limit, limit=MAX_JSON_NESTING),
            MAX_JSON_NESTING,
        )
        self.assertGreater(
            max_container_depth(over_limit, limit=MAX_JSON_NESTING),
            MAX_JSON_NESTING,
        )
        # Depth 512 still parses. The interpreter is not what rejects it.
        self.assertIsInstance(json.loads(at_limit), list)
        quoted = '{"note": "' + ("{" * 600) + '"}'
        self.assertEqual(max_container_depth(quoted), 1)
        escaped = '{"note": "say \\"{\\" still"}'
        self.assertEqual(max_container_depth(escaped), 1)

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "in.csv"
            side = Path(folder) / "in.csv.source.json"
            side.write_text(at_limit, encoding="utf-8")
            self.assertIsNone(sidecar_window(source, "0" * 64))
            side.write_text(over_limit, encoding="utf-8")
            with self.assertRaises(AnalysisWindowError) as caught:
                sidecar_window(source, "0" * 64)
            self.assertIn("is not valid JSON", str(caught.exception))
            self.assertNotIn("Traceback", str(caught.exception))

    def test_non_str_raises_type_error(self):
        for value in (None, b"[]", 1):
            with self.assertRaises(TypeError):
                max_container_depth(value)


if __name__ == "__main__":
    unittest.main()
