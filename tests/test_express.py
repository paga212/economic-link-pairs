"""Offline unit tests for the expression selector (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.express import RISK_BUDGET, STOP, build_idea  # noqa: E402


def liquid_bars(px=50.0, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), px, 1_000_000.0) for i in range(63)]  # $50M ADV


class TestExpress(unittest.TestCase):
    def _bars(self, extra=None):
        b = {"S": liquid_bars(), "SPY": liquid_bars(400.0), "CP": liquid_bars()}
        if extra:
            b.update(extra)
        return b

    def test_pairs_with_liquid_opposite_counterpart(self):
        # primary long S; CP is signaling short and liquid -> stock pair, opposite directions.
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, date(2020, 3, 1), self._bars(), {"CP": -0.08}, set())
        self.assertEqual(idea["expression"], "stock-pair")
        self.assertEqual(idea["primary"]["direction"], 1)
        self.assertEqual(idea["neutralizer"]["ticker"], "CP")
        self.assertEqual(idea["neutralizer"]["direction"], -1)   # opposite the primary
        self.assertEqual(idea["primary"]["notional"], idea["neutralizer"]["notional"])  # dollar-neutral

    def test_hedges_when_no_liquid_counterpart(self):
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, date(2020, 3, 1), self._bars(), {}, set())  # no signaling counterpart
        self.assertEqual(idea["expression"], "stock-hedge")
        self.assertEqual(idea["neutralizer"]["ticker"], "SPY")
        self.assertEqual(idea["neutralizer"]["direction"], -1)

    def test_skips_used_counterpart(self):
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, date(2020, 3, 1), self._bars(), {"CP": -0.08}, {"CP"})
        self.assertEqual(idea["expression"], "stock-hedge")   # CP taken -> hedge

    def test_risk_budget_sizes_primary_notional(self):
        # cash long, stop = STOP -> notional = RISK_BUDGET / STOP
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, date(2020, 3, 1), self._bars(), {}, set())
        self.assertAlmostEqual(idea["primary"]["notional"], RISK_BUDGET / STOP)

    def test_short_primary_is_a_snapped_put_spread(self):
        view = {"supplier": "S", "customer": "C", "side": -1, "entry_px": 129.06, "iv": 0.4}
        b = {"S": liquid_bars(129.06), "SPY": liquid_bars(400.0)}
        idea = build_idea(view, date(2020, 3, 1), b, {}, set())
        self.assertEqual(idea["primary"]["instrument"], "spread")
        self.assertEqual(idea["primary"]["k_long"], 129.0)     # snapped from 129.06
        self.assertTrue(idea["primary"]["k_short"] < idea["primary"]["k_long"])


if __name__ == "__main__":
    unittest.main()
