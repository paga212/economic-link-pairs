"""Offline unit tests for the daily per-trade engine (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.trades import simulate  # noqa: E402


def series(prices, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), float(p)) for i, p in enumerate(prices)]


class TestTrades(unittest.TestCase):
    LB = 5  # short lookback so the synthetic cases are tractable

    def test_long_trailing_stop(self):
        # customer jumps +10% at day 10 -> long entry; supplier peaks +20% then falls through
        # the trailing stop (peak 0.20 - trail 0.05 = 0.15) to +9%.
        cust = [100] * 10 + [110] * 7
        supp = [100] * 10 + [100, 106, 112, 120, 116, 109, 107]
        closed, _ = simulate([("S", "C")], {"C": series(cust), "S": series(supp)}, lookback=self.LB)
        self.assertEqual(len(closed), 1)
        t = closed[0]
        self.assertEqual(t["side"], 1)
        self.assertEqual(t["reason"], "trail_stop")
        self.assertAlmostEqual(t["ret"], 0.09, places=2)  # first close below peak(0.20) - trail(0.05)

    def test_signal_exit(self):
        # customer jumps (+10%, long entry) then reverts below its 5-day-ago level -> signal exit
        cust = [100] * 10 + [110] * 5 + [95, 95]
        supp = [100] * 17  # flat -> no stop
        closed, _ = simulate([("S", "C")], {"C": series(cust), "S": series(supp)}, lookback=self.LB)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "signal")
        self.assertAlmostEqual(closed[0]["ret"], 0.0, places=6)

    def test_short_entry_on_customer_drop(self):
        cust = [100] * 10 + [90] * 5  # -10% -> short entry
        supp = [100] * 15
        closed, openn = simulate([("S", "C")], {"C": series(cust), "S": series(supp)}, lookback=self.LB)
        opened = (openn + closed)
        self.assertTrue(opened and opened[0]["side"] == -1)

    def test_no_entry_below_threshold(self):
        cust = [100] * 10 + [102] * 5  # +2% < 5% enter -> no trade
        supp = [100] * 15
        closed, openn = simulate([("S", "C")], {"C": series(cust), "S": series(supp)}, lookback=self.LB)
        self.assertEqual(len(closed) + len(openn), 0)


if __name__ == "__main__":
    unittest.main()
