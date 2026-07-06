"""Offline tests for the Risk/Borrow agent (no network; fetches + LLM monkeypatched)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import elp.risk as risk  # noqa: E402
from elp.risk import borrow_class, next_earnings_est, reported_since_entry  # noqa: E402


class TestPure(unittest.TestCase):
    def test_borrow_class(self):
        # non-short stock leg -> na
        self.assertEqual(borrow_class("GILD", 1, "stock", 5e10, 1e8), "na")
        # short spread -> na (only short STOCK needs borrow)
        self.assertEqual(borrow_class("PG", -1, "spread", 5e10, 1e8), "na")
        # short ETF hedge -> easy
        self.assertEqual(borrow_class("SPY", -1, "stock", None, 0.0), "easy")
        # short large-cap liquid stock -> easy
        self.assertEqual(borrow_class("VC", -1, "stock", 5e9, 5e7), "easy")
        # short small-cap stock -> hard
        self.assertEqual(borrow_class("MZTI", -1, "stock", 5e8, 1e6), "hard")
        # missing marketcap -> hard (conservative)
        self.assertEqual(borrow_class("MZTI", -1, "stock", None, 5e7), "hard")

    def test_next_earnings_est_future_and_past_last_announce(self):
        # last period end 2026-03-31; +40d announce = 2026-05-10 < today -> next = +131d
        d, days = next_earnings_est(["2026-03-31"], date(2026, 7, 5))
        self.assertEqual(d, date(2026, 8, 9))
        self.assertEqual(days, 35)
        # last period end 2026-06-28; +40d = 2026-08-07 >= today -> that IS next
        d2, _ = next_earnings_est(["2026-06-28"], date(2026, 7, 5))
        self.assertEqual(d2, date(2026, 8, 7))
        # no dates -> (None, None)
        self.assertEqual(next_earnings_est([], date(2026, 7, 5)), (None, None))

    def test_reported_since_entry(self):
        # last announce 2026-05-10; entry 2026-04-01 < 2026-05-10 <= today -> True
        self.assertTrue(reported_since_entry(["2026-03-31"], date(2026, 4, 1), date(2026, 7, 5)))
        # entry AFTER the last announce -> False
        self.assertFalse(reported_since_entry(["2026-03-31"], date(2026, 6, 1), date(2026, 7, 5)))
        self.assertFalse(reported_since_entry([], date(2026, 4, 1), date(2026, 7, 5)))


if __name__ == "__main__":
    unittest.main()
