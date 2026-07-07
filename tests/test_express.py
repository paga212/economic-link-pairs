"""Offline unit tests for the expression selector (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.express import (BETA_MAX, BETA_MIN, RISK_BUDGET, STOP, _clamp_beta, build_idea,  # noqa: E402
                         describe_leg)


def liquid_bars(px=50.0, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), px, 1_000_000.0) for i in range(63)]  # $50M ADV


class TestClampBeta(unittest.TestCase):
    def test_clamps_degenerate_and_extreme_betas(self):
        self.assertEqual(_clamp_beta(0.0085), BETA_MIN)   # PG's degenerate ~0.01 -> floor
        self.assertEqual(_clamp_beta(-0.4), BETA_MIN)     # negative -> floor
        self.assertEqual(_clamp_beta(5.0), BETA_MAX)      # spurious high -> ceiling
        self.assertEqual(_clamp_beta(0.6), 0.6)           # sane value untouched


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

    def test_neutralizer_priced_at_entry_day_not_last_bar(self):
        # CP rises 50 -> 112 over the window; entry is the middle day. The neutralizer must be
        # priced at the entry-day close, not the last bar (the historical bug used bars[cp][-1]).
        cp_bars = [(date(2020, 1, 1) + timedelta(days=i), 50.0 + i, 1_000_000.0) for i in range(63)]
        entry = date(2020, 1, 1) + timedelta(days=30)          # close that day = 80.0
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, entry, self._bars({"CP": cp_bars}), {"CP": -0.08}, set())
        self.assertEqual(idea["neutralizer"]["ticker"], "CP")
        self.assertEqual(idea["neutralizer"]["entry_px"], 80.0)   # entry-day close, not 112.0

    def test_short_primary_is_a_snapped_put_spread(self):
        view = {"supplier": "S", "customer": "C", "side": -1, "entry_px": 129.06, "iv": 0.4}
        b = {"S": liquid_bars(129.06), "SPY": liquid_bars(400.0)}
        idea = build_idea(view, date(2020, 3, 1), b, {}, set())
        self.assertEqual(idea["primary"]["instrument"], "spread")
        self.assertEqual(idea["primary"]["k_long"], 129.0)     # snapped from 129.06
        self.assertTrue(idea["primary"]["k_short"] < idea["primary"]["k_long"])


class TestDescribeLeg(unittest.TestCase):
    def test_long_stock_shows_shares_price_and_notional(self):
        leg = {"role": "primary", "ticker": "GILD", "direction": 1, "instrument": "stock",
               "notional": 200000.0, "entry_px": 123.84}
        s = describe_leg(leg)
        self.assertIn("long", s)
        self.assertIn("1,615 sh", s)          # round(200000/123.84)
        self.assertIn("GILD", s)
        self.assertIn("$123.84", s)
        self.assertIn("$200k", s)

    def test_short_bear_put_spread_states_structure_and_risk(self):
        leg = {"role": "primary", "ticker": "PG", "direction": -1, "instrument": "spread",
               "notional": 200000.0, "entry_px": 147.4, "S0": 147.4, "k_long": 147.0,
               "k_short": 133.0, "debit": 3.60, "dte": 45}
        s = describe_leg(leg)
        self.assertIn("bear put spread", s)
        self.assertIn("buy 147P", s)          # long the higher-strike put
        self.assertIn("sell 133P", s)         # short the lower-strike put
        self.assertIn("exp 45d", s)           # DTE spelled out, not "45DTE"
        self.assertIn("14 spreads", s)        # round(200000/(100*147.4))
        self.assertIn("max risk", s)

    def test_neutralizer_tags_pair_vs_hedge(self):
        pair = {"role": "neutralizer", "ticker": "VC", "direction": -1, "instrument": "stock",
                "notional": 200000.0, "entry_px": 102.45}
        self.assertIn("pair", describe_leg(pair, "stock-pair"))
        hedge = {"role": "neutralizer", "ticker": "SPY", "direction": 1, "instrument": "stock",
                 "notional": 60000.0, "entry_px": 744.78}
        h = describe_leg(hedge, "stock-hedge")
        self.assertIn("hedge", h)             # β-hedge tag
        self.assertIn("81 sh", h)             # round(60000/744.78)


if __name__ == "__main__":
    unittest.main()
