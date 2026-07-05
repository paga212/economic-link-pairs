"""Offline sanity tests for the compact Black-Scholes / bear-put-spread pricer."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.options import bear_put_spread, bs_put  # noqa: E402


class TestOptions(unittest.TestCase):
    def test_put_positive_and_intrinsic_floor(self):
        self.assertGreater(bs_put(100, 100, 0.25, 0.4), 0)     # ATM put has value
        self.assertAlmostEqual(bs_put(80, 100, 0.0, 0.4), 20)  # expiry -> intrinsic

    def test_spread_bounded(self):
        K1, K2 = 100, 90
        v = bear_put_spread(100, K1, K2, 0.25, 0.4)
        self.assertTrue(0 < v < (K1 - K2))                     # ATM: between 0 and width

    def test_spread_deep_itm_near_width(self):
        # underlying far below both strikes -> spread ~ width (discounted)
        v = bear_put_spread(50, 100, 90, 0.10, 0.4)
        self.assertGreater(v, 9.0)
        self.assertLessEqual(v, 10.0)

    def test_spread_far_otm_near_zero(self):
        self.assertLess(bear_put_spread(200, 100, 90, 0.25, 0.4), 0.5)


class TestSnapStrike(unittest.TestCase):
    def test_grid_increments(self):
        from elp.options import snap_strike
        self.assertEqual(snap_strike(129.06), 129.0)   # $1 grid in the $25-200 band
        self.assertEqual(snap_strike(143.40), 143.0)
        self.assertEqual(snap_strike(23.30), 23.5)     # $0.50 grid under $25
        self.assertEqual(snap_strike(421.54), 420.0)   # $5 grid at/above $200


if __name__ == "__main__":
    unittest.main()
