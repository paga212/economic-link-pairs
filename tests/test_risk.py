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


class TestOrchestration(unittest.TestCase):
    def tearDown(self):
        risk.complete = _ORIG_COMPLETE
        risk.assess_idea_risk = _ORIG_ASSESS
        risk.narrate = _ORIG_NARRATE

    def _bars(self, t):  # liquid stub: (date, price, volume) x 63, $50M ADV
        return [(date(2026, 1, 1), 50.0, 1_000_000.0)] * 63

    def test_long_pair_flags_hard_borrow_on_small_neutralizer(self):
        idea = {"supplier": "GILD", "customer": "CAH", "side": 1, "entry": "2026-06-25",
                "primary": {"role": "primary", "ticker": "GILD", "direction": 1, "instrument": "stock"},
                "neutralizer": {"role": "neutralizer", "ticker": "MZTI", "direction": -1, "instrument": "stock"}}
        facts = risk.assess_idea_risk(idea, bars_fn=self._bars,
                                      mktcap_fn=lambda t: 5e8,          # small cap -> hard
                                      dates_fn=lambda t: ["2026-03-31"], today=date(2026, 7, 5))
        self.assertEqual(facts["borrow"]["ticker"], "MZTI")
        self.assertEqual(facts["borrow"]["class"], "hard")
        self.assertEqual(facts["liquidity"], "ok")

    def test_short_spread_idea_has_no_borrow(self):
        idea = {"supplier": "PG", "customer": "WMT", "side": -1, "entry": "2026-07-01",
                "primary": {"role": "primary", "ticker": "PG", "direction": -1, "instrument": "spread"},
                "neutralizer": {"role": "neutralizer", "ticker": "SPY", "direction": 1, "instrument": "stock"}}
        facts = risk.assess_idea_risk(idea, bars_fn=self._bars, mktcap_fn=lambda t: 5e9,
                                      dates_fn=lambda t: [], today=date(2026, 7, 5))
        self.assertEqual(facts["borrow"]["class"], "na")

    def test_assess_degrades_when_fetch_raises(self):
        def boom(t): raise RuntimeError("net down")
        idea = {"supplier": "GILD", "customer": "CAH", "side": 1, "entry": "2026-06-25",
                "primary": {"ticker": "GILD", "direction": 1, "instrument": "stock"},
                "neutralizer": {"ticker": "MZTI", "direction": -1, "instrument": "stock"}}
        facts = risk.assess_idea_risk(idea, bars_fn=boom, mktcap_fn=boom, dates_fn=boom,
                                      today=date(2026, 7, 5))            # must NOT raise
        self.assertEqual(facts["liquidity"], "thin")

    def test_narrate_fails_soft(self):
        def boom(*a, **k): raise risk.AnthropicError("HTTP 500", code=500)
        risk.complete = boom
        self.assertEqual(risk.narrate({"supplier": "X", "customer": "Y"}, {}), "")

    def test_narrate_fail_soft_on_malformed_idea(self):
        self.assertEqual(risk.narrate({}, {"borrow": {"class": "na"}}), "")   # missing supplier/customer

    def test_build_risk_keys_every_idea(self):
        risk.assess_idea_risk = lambda o, **k: {"borrow": {"ticker": None, "class": "na"},
            "earnings": {"days_to": 30, "reported_since_entry": False}, "liquidity": "ok"}
        risk.narrate = lambda idea, facts: ""
        state = {"open": [{"supplier": "GILD", "customer": "CAH"}, {"supplier": "PG", "customer": "WMT"}]}
        out = risk.build_risk(state)
        self.assertEqual(set(out["per_idea"]), {"GILD|CAH", "PG|WMT"})
        self.assertEqual(out["model_used"], risk.OPUS)

    def test_risk_flag_precedence(self):
        self.assertIn("hard to borrow", risk.risk_flag({"borrow": {"class": "hard"}}))
        self.assertIn("post-earnings", risk.risk_flag({"borrow": {"class": "na"},
            "earnings": {"reported_since_entry": True}}))
        self.assertIn("thin", risk.risk_flag({"borrow": {"class": "na"},
            "earnings": {"reported_since_entry": False}, "liquidity": "thin"}))
        self.assertEqual(risk.risk_flag(None), "")


_ORIG_COMPLETE = None
_ORIG_ASSESS = None
_ORIG_NARRATE = None


def setUpModule():
    global _ORIG_COMPLETE, _ORIG_ASSESS, _ORIG_NARRATE
    _ORIG_COMPLETE, _ORIG_ASSESS, _ORIG_NARRATE = risk.complete, risk.assess_idea_risk, risk.narrate


if __name__ == "__main__":
    unittest.main()
