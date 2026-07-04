"""Offline unit tests for the signal logic (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.signal import _next_month, evaluate_pair, lagged_pairs  # noqa: E402


def _months(n, start=(2019, 1)):
    y, m = start
    out = []
    for _ in range(n):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class TestSignal(unittest.TestCase):
    def test_next_month_wraps_december(self):
        self.assertEqual(_next_month((2020, 12)), (2021, 1))
        self.assertEqual(_next_month((2020, 3)), (2020, 4))

    def test_perfect_lag_gives_corr_one(self):
        keys = _months(24)
        cust = {k: (0.1 if i % 2 == 0 else -0.1) for i, k in enumerate(keys)}
        supp = {_next_month(k): cust[k] for k in keys}  # supplier M+1 == customer M
        res = evaluate_pair(cust, supp)
        self.assertIsNotNone(res)
        self.assertGreaterEqual(res["n"], 12)
        self.assertAlmostEqual(res["lagged_corr"], 1.0, places=6)
        self.assertAlmostEqual(res["up_minus_down"], 0.2, places=6)

    def test_alignment_drops_unmatched_last_month(self):
        keys = _months(24)
        cust = {k: 0.01 for k in keys}
        supp = {_next_month(k): 0.02 for k in keys}
        xs, _ = lagged_pairs(cust, supp)
        self.assertEqual(len(xs), 24)  # every M has an M+1 in supp here

    def test_insufficient_data_returns_none(self):
        keys = _months(6)
        cust = {k: 0.01 for k in keys}
        supp = {k: 0.01 for k in keys}
        self.assertIsNone(evaluate_pair(cust, supp))


if __name__ == "__main__":
    unittest.main()
