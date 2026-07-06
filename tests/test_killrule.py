"""Offline tests for the Phase-5 kill-rule scorecard (pure; no I/O)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.killrule import scorecard, scorecard_line, sharpe  # noqa: E402


def _closed(rets):
    return [{"ret_net": r, "entry": "2026-02-01"} for r in rets]


class TestSharpe(unittest.TestCase):
    def test_known_series(self):
        # [0.01,0.03]: mean 0.02, pstdev 0.01 -> per-trade 2.0; annualize sqrt(2/1) -> 2*sqrt(2)
        self.assertAlmostEqual(sharpe([0.01, 0.03], 1.0), 2.0 * 2 ** 0.5, places=6)

    def test_degenerate(self):
        self.assertIsNone(sharpe([0.02], 1.0))          # < 2 trades
        self.assertIsNone(sharpe([0.02, 0.02], 1.0))    # zero variance
        self.assertIsNone(sharpe([0.01, 0.03], 0.0))    # non-positive years


class TestScorecard(unittest.TestCase):
    def test_pending_before_gate(self):
        state = {"closed": _closed([0.01] * 5), "open": [{}]}
        sc = scorecard(state, date(2026, 7, 4), date(2027, 1, 4))   # ~6 months, 5 closed
        self.assertEqual(sc["verdict"], "PENDING")
        self.assertFalse(sc["gate_open"])

    def test_pass_when_gate_open_and_all_met(self):
        rets = [0.005, 0.015] * 33                       # 66 closed, mean 0.01, sd 0.005
        state = {"closed": _closed(rets), "open": []}
        sc = scorecard(state, date(2026, 1, 1), date(2027, 2, 1))   # ~13 months, 66 trades
        self.assertTrue(sc["gate_open"])
        self.assertTrue(sc["sharpe_ok"] and sc["expectancy_ok"] and sc["volume_ok"])
        self.assertEqual(sc["verdict"], "PASS")

    def test_fail_on_negative_expectancy(self):
        rets = [-0.005, -0.015] * 33                     # negative mean
        state = {"closed": _closed(rets), "open": []}
        sc = scorecard(state, date(2026, 1, 1), date(2027, 2, 1))
        self.assertTrue(sc["gate_open"])
        self.assertFalse(sc["expectancy_ok"])
        self.assertEqual(sc["verdict"], "FAIL")

    def test_zero_closed_is_pending_and_safe(self):
        sc = scorecard({"closed": [], "open": [{}, {}]}, date(2026, 7, 4), date(2026, 7, 5))
        self.assertIsNone(sc["expectancy"])
        self.assertIsNone(sc["sharpe"])
        self.assertEqual(sc["verdict"], "PENDING")

    def test_scorecard_line_has_verdict(self):
        sc = scorecard({"closed": [], "open": []}, date(2026, 7, 4), date(2026, 7, 5))
        line = scorecard_line(sc)
        self.assertIn("Kill rule:", line)
        self.assertIn("PENDING", line)


if __name__ == "__main__":
    unittest.main()
