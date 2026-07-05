"""Offline unit tests for Tiingo row parsing (no network)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.tiingo import _parse_bars  # noqa: E402


class TestParseBars(unittest.TestCase):
    def test_parses_date_close_volume(self):
        rows = [{"date": "2020-01-02T00:00:00.000Z", "adjClose": 100.0, "adjVolume": 1_000_000},
                {"date": "2020-01-03T00:00:00.000Z", "adjClose": 101.0, "adjVolume": 2_000_000}]
        out = _parse_bars(rows)
        self.assertEqual(out[0], (date(2020, 1, 2), 100.0, 1_000_000.0))
        self.assertEqual(out[1][2], 2_000_000.0)

    def test_falls_back_to_raw_volume(self):
        rows = [{"date": "2020-01-02T00:00:00.000Z", "adjClose": 50.0, "volume": 500_000}]
        self.assertEqual(_parse_bars(rows)[0], (date(2020, 1, 2), 50.0, 500_000.0))


if __name__ == "__main__":
    unittest.main()
