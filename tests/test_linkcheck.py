"""Offline unit tests for link validation (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.linkcheck import _price_ok  # noqa: E402


def bars(prices, vol=1_000_000.0, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), float(p), vol) for i, p in enumerate(prices)]


class TestPriceOk(unittest.TestCase):
    def test_clean_liquid_series_ok(self):
        ok, reason = _price_ok(bars([50] * 63))          # $50, $50M ADV
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_empty_series(self):
        self.assertEqual(_price_ok([]), (False, "no_data"))

    def test_penny_or_illiquid(self):
        self.assertEqual(_price_ok(bars([0.07] * 63))[1], "illiquid")   # sub-$5

    def test_glitch_bar_flagged(self):
        # a $0.07 bar among $115 bars -> >5x adjacent jump (the MZTI case)
        px = [115] * 30 + [0.07] + [115] * 32
        self.assertEqual(_price_ok(bars(px))[1], "bad_bars")


if __name__ == "__main__":
    unittest.main()
