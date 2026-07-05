"""Offline unit tests for the daily per-trade engine (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.trades import describe_open, net_return, simulate  # noqa: E402


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


    def test_describe_open_stock(self):
        # LONG stock: entry price exposed, no spread fields, live return = px/entry - 1.
        t = {"supplier": "S", "customer": "C", "side": 1, "instrument": "stock",
             "entry_date": date(2026, 6, 1), "entry_px": 100.0, "peak": 0.10}
        row = describe_open(t, 110.0, date(2026, 6, 20))
        self.assertEqual(row["kind"], "LONG stock")
        self.assertEqual(row["entry_px"], 100.0)
        self.assertEqual(row["days"], 19)
        self.assertAlmostEqual(row["ret"], 0.10, places=9)
        self.assertNotIn("k_long", row)              # stock carries no strikes

    def test_describe_open_spread(self):
        # SHORT bear-put-spread: strikes, premium, DTE, entry spot all exposed.
        t = {"supplier": "S", "customer": "C", "side": -1, "instrument": "spread",
             "entry_date": date(2026, 6, 1), "entry_px": 50.0, "peak": 0.02,
             "S0": 50.0, "K1": 50.0, "K2": 45.0, "T0": 45 / 365, "iv": 0.4, "dte": 45,
             "debit": 1.5}
        row = describe_open(t, 48.0, date(2026, 6, 20))
        self.assertEqual(row["kind"], "SHORT put-spread")
        self.assertEqual((row["k_long"], row["k_short"]), (50.0, 45.0))
        self.assertEqual(row["debit"], 1.5)
        self.assertEqual(row["spot0"], 50.0)
        self.assertEqual(row["dte"], 45)
        self.assertIsInstance(row["ret"], float)

    def test_net_return_costs(self):
        # long: only round-trip transaction cost (no borrow)
        lng = {"side": 1, "ret": 0.10, "days": 30}
        self.assertAlmostEqual(net_return(lng, spread_bps=25, borrow_apr=0.05),
                               0.10 - 2 * 25 / 1e4, places=9)  # -50bps
        # short: transaction cost + borrow prorated by days
        sht = {"side": -1, "ret": 0.10, "days": 73}
        self.assertAlmostEqual(net_return(sht, spread_bps=25, borrow_apr=0.05),
                               0.10 - 2 * 25 / 1e4 - 0.05 * 73 / 365, places=9)  # -50bps -1%


class TestIdeaReturn(unittest.TestCase):
    def _idea(self, neut_notional):
        from elp.express import RISK_BUDGET, STOP
        n = RISK_BUDGET / STOP
        return {"entry_date": date(2020, 1, 1),
                "primary": {"ticker": "S", "direction": 1, "instrument": "stock",
                            "notional": n, "entry_px": 100.0},
                "neutralizer": {"ticker": "H", "direction": -1, "instrument": "stock",
                                "notional": neut_notional, "entry_px": 50.0}}

    def test_dollar_neutral_pair_nets_the_two_legs(self):
        from elp.express import RISK_BUDGET, STOP
        from elp.trades import idea_return
        idea = self._idea(RISK_BUDGET / STOP)          # equal notionals
        # long S +10%, short H where H +4% -> short loses 4%; net = +10% - 4% = +6%
        ret, expired = idea_return(idea, {"S": 110.0, "H": 52.0}, date(2020, 1, 20))
        self.assertAlmostEqual(ret, 0.06, places=6)
        self.assertFalse(expired)

    def test_beta_weighted_hedge(self):
        from elp.express import RISK_BUDGET, STOP
        from elp.trades import idea_return
        n = RISK_BUDGET / STOP
        idea = self._idea(0.5 * n)                     # beta 0.5 hedge
        # long S +10%; short H +10% weighted 0.5 -> -5%; net +5%
        ret, _ = idea_return(idea, {"S": 110.0, "H": 55.0}, date(2020, 1, 20))
        self.assertAlmostEqual(ret, 0.05, places=6)


if __name__ == "__main__":
    unittest.main()
