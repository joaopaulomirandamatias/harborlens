"""Acceptance checks for the static UI prototype copy (SPEC-006 design input).

The prototype in ``prototypes/ui/HarborLensPrototype.jsx`` is a single React
file with fictional example data. It is not an implementation of FR-017 or
FR-018. These tests read the source text only; they need no Node toolchain.

Covered rules:

* NFR-001: the persistent NOT FOR NAVIGATION banner text is present once.
* BR-001: the words for a confirmed facility visit or a confirmed vessel
  activity appear only inside that banner, where they are negated.
* BR-001 / BR-018: every stop carries the "Não validada" badge with the
  tooltip "Ainda sem confirmação independente"; an "example data" badge exists.
* BR-016 / SPEC-001 synthetic-id rule: the only nine-digit vessel ids are the
  unassigned MID 199 range 199000101-199000112.
* NFR-016: ``prefers-reduced-motion`` is handled, and the map triangle uses a
  light violet with at least 3:1 contrast against the map land and water.
* The reproduction command is the one the README documents.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototypes" / "ui" / "HarborLensPrototype.jsx"
README = ROOT / "README.md"

BANNER = (
    "Somente para pesquisa histórica — não use para navegação (NOT FOR NAVIGATION). "
    "As paradas mostradas não são atracações, fundeios ou escalas confirmadas."
)
FORBIDDEN = re.compile(r"escala|atraca|fundeio|port\s*call|ancoradouro", re.IGNORECASE)
CLI_COMMAND = "harborlens --input tests/fixtures/synthetic_ais.csv --out results"


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class UiPrototypeCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_banner_present_exactly_once(self) -> None:
        self.assertEqual(self.text.count(BANNER), 1)

    def test_forbidden_terms_only_inside_negated_banner(self) -> None:
        outside = self.text.replace(BANNER, "")
        self.assertEqual(FORBIDDEN.findall(outside), [])

    def test_unvalidated_badge_and_tooltip(self) -> None:
        self.assertIn('content="Ainda sem confirmação independente"', self.text)
        self.assertIn("Não validada", self.text)
        self.assertIn("Dados de exemplo", self.text)

    def test_only_unassigned_mid_199_vessel_ids(self) -> None:
        ids = set(re.findall(r"(?<![\d.])(\d{9})(?!\d)", self.text))
        self.assertEqual(ids, {"199000100"})
        self.assertIn("String(199000100 + s.n)", self.text)
        self.assertEqual(len(re.findall(r"\{ n: \d+, start:", self.text)), 12)

    def test_reduced_motion_supported(self) -> None:
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.text)
        self.assertIn('"(prefers-reduced-motion: reduce)"', self.text)
        self.assertIn("selected && !reduced", self.text)

    def test_map_triangle_contrast_at_least_3_to_1(self) -> None:
        triangle = re.search(r'dark: \{ completa: "#[0-9a-f]{6}", borda: "#[0-9a-f]{6}", desconhecida: "(#[0-9a-f]{6})" \}', self.text)
        land = re.search(r'land: "(#[0-9a-f]{6})"', self.text)
        water = re.search(r'water: "(#[0-9a-f]{6})"', self.text)
        self.assertIsNotNone(triangle)
        for ground in (land, water):
            self.assertIsNotNone(ground)
            self.assertGreaterEqual(_contrast(triangle.group(1), ground.group(1)), 3.0)

    def test_cli_command_matches_readme(self) -> None:
        self.assertIn(f'const CLI_COMMAND = "{CLI_COMMAND}";', self.text)
        self.assertIn(CLI_COMMAND, README.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
