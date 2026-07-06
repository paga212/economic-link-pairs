"""Offline tests for the trade-detail viz (pure; no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.tradeviz import svg_line  # noqa: E402


class TestSvg(unittest.TestCase):
    def test_line_renders_polyline_and_entry_marker(self):
        svg = svg_line([{"pts": [(0, 1.0), (1, 2.0), (2, 1.5)], "cls": "pv", "dash": False}],
                       entry_idx=1)
        self.assertIn("<svg", svg)
        self.assertIn("<polyline", svg)
        self.assertIn('class="pv"', svg)
        self.assertIn("class=entry", svg)          # vertical entry marker

    def test_dashed_series_has_dasharray(self):
        svg = svg_line([{"pts": [(0, 1.0), (1, 1.1)], "cls": "hyp", "dash": True}])
        self.assertIn("stroke-dasharray", svg)

    def test_empty_is_placeholder(self):
        self.assertIn("no data", svg_line([{"pts": [], "cls": "x", "dash": False}]))


if __name__ == "__main__":
    unittest.main()
