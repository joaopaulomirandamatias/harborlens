"""Boundary tests for the shared JSON container-depth counter."""
import json
import tempfile
import time
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

    def test_limit_returns_when_the_depth_first_passes_it(self):
        """The early return stops at limit + 1 and does not read a later nest.

        A full walk of the same text reports the later, deeper nest. Removing
        the ``limit`` return would report that later depth instead of
        ``limit + 1``.
        """
        limit = 4
        text = ("[" * (limit + 1)) + ("]" * (limit + 1)) + ("[" * 9) + ("]" * 9)
        self.assertEqual(max_container_depth(text), 9)
        self.assertEqual(max_container_depth(text, limit=limit), limit + 1)
        deep_tail = "[" * MAX_JSON_NESTING + "]" * MAX_JSON_NESTING
        deep_tail += "[" * (MAX_JSON_NESTING + 40) + "]" * (MAX_JSON_NESTING + 40)
        self.assertEqual(max_container_depth(deep_tail), MAX_JSON_NESTING + 40)
        self.assertEqual(
            max_container_depth(deep_tail, limit=MAX_JSON_NESTING),
            MAX_JSON_NESTING + 1,
        )

    def test_limited_scan_stays_inside_a_generous_time_budget(self):
        """A limited scan of a long bracket run stays well under the budget.

        The budget is loose on purpose so a slow CI runner does not flake.
        The early return walks 513 brackets. The unlimited sizes below check
        that a longer input does not jump by a large factor.
        """
        huge = "[" * 5_000_000
        started = time.perf_counter()
        depth = max_container_depth(huge, limit=MAX_JSON_NESTING)
        limited = time.perf_counter() - started
        self.assertEqual(depth, MAX_JSON_NESTING + 1)
        self.assertLess(limited, 30.0)
        durations = []
        for count in (20_000, 40_000, 80_000):
            sample = "[" * count + "]" * count
            started = time.perf_counter()
            self.assertEqual(max_container_depth(sample), count)
            durations.append(time.perf_counter() - started)
        self.assertLess(durations[-1], 5.0)
        self.assertLess(durations[-1], max(1.0, durations[0] * 40))


if __name__ == "__main__":
    unittest.main()
