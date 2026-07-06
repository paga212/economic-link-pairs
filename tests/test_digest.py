"""Offline unit tests for the Master/Orchestrator digest (no network).

The LLM call is monkeypatched, so these exercise prompt construction, the deterministic
merge (ordering, hallucination-dropping, number preservation, mandatory caveat), and the
Fable-5 -> Opus fallback logic — never touching the API.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import elp.digest as digest  # noqa: E402
import elp.llm as llm  # noqa: E402
from elp.digest import CAVEAT, _prompt, build_digest  # noqa: E402
from elp.llm import AnthropicError, complete_fallback  # noqa: E402

STATE = {
    "open": [
        {"supplier": "SWKS", "customer": "AAPL", "kind": "LONG stock", "days": 12,
         "ret": 0.0834, "stop": 0.0334},
        {"supplier": "AXL", "customer": "GM", "kind": "SHORT put-spread", "days": 3,
         "ret": -0.0210, "stop": -0.05},
    ],
    "closed": [],
    "stats": {"n": 0, "win_rate": None, "mean_ret": None},
}
# Keyed by (supplier, customer) — a supplier may name several customers; the note must match
# the customer actually traded, not just the supplier.
NOTES = {("SWKS", "AAPL"): "Skyworks — Apple", ("AXL", "GM"): "American Axle — GM"}


class TestPrompt(unittest.TestCase):
    def test_prompt_lists_every_open_trade_and_closed_count(self):
        p = _prompt(STATE, NOTES)
        self.assertIn("SWKS", p)
        self.assertIn("AXL", p)
        self.assertIn("Skyworks — Apple", p)      # link note is included as context
        self.assertIn("n=0", p)                     # closed count surfaced
        self.assertIn("JSON", p)                    # asks for structured output
        self.assertIn("attention", p.lower())       # merged-watch: flag concerns inline, no list

    def test_prompt_handles_no_open_trades(self):
        p = _prompt({"open": [], "stats": {}}, {})
        self.assertIn("none open", p)

    def test_prompt_handles_idea_shaped_rows_without_kind(self):
        # Regression: idea-shaped open rows (post two-legged refactor) may lack "kind" but
        # always carry "side" -- _prompt must derive kind rather than KeyError.
        state = {"open": [{"supplier": "TTWO", "customer": "AAPL", "side": -1,
                           "expression": "stock-hedge", "days": 8, "ret": -0.02}], "stats": {}}
        p = _prompt(state, {})            # must NOT raise KeyError
        self.assertIn("TTWO", p)
        self.assertIn("SHORT", p)          # derived from side

    def test_prompt_includes_catalyst_when_supplied(self):
        catalyst = {"SWKS|AAPL": {"customer_catalyst": "none", "confounding": "yes"}}
        p = _prompt(STATE, NOTES, catalyst)
        self.assertIn("catalyst=none", p)
        self.assertIn("confounded=yes", p)
        self.assertIn("rank", p.lower())         # instruction to down-rank exists

    def test_prompt_includes_risk_when_supplied(self):
        risk = {"SWKS|AAPL": {"borrow": {"class": "hard"},
                              "earnings": {"reported_since_entry": True}, "liquidity": "thin"}}
        p = _prompt(STATE, NOTES, None, risk)
        self.assertIn("borrow=hard", p)
        self.assertIn("earnings=post-earnings", p)
        self.assertIn("liq=thin", p)
        self.assertIn("options", p.lower())      # instruction mentions the options fallback

    def test_note_matches_traded_customer_not_another(self):
        # Regression: a supplier with two customers; the trade is on one of them. The note beside
        # it must be THAT customer's note, not the other's (the (supplier,customer) keying fix).
        state = {"open": [{"supplier": "VC", "customer": "F", "kind": "SHORT put-spread",
                           "days": 8, "ret": 0.0, "stop": -0.05}], "stats": {}}
        notes = {("VC", "F"): "Visteon — Ford", ("VC", "GM"): "Visteon — GM"}
        p = _prompt(state, notes)
        self.assertIn("Visteon — Ford", p)
        self.assertNotIn("Visteon — GM", p)


class TestBuildDigest(unittest.TestCase):
    def _patch_llm(self, reply):
        digest.complete_fallback = lambda *a, **k: (reply, "claude-fable-5")

    def tearDown(self):
        digest.complete_fallback = complete_fallback   # restore

    def test_reorders_by_model_ranking_and_keeps_state_numbers(self):
        # Model ranks AXL first; every number must still come from STATE, not the model.
        self._patch_llm(json.dumps({
            "summary": "Two-name book.",
            "ranked": [{"supplier": "AXL", "rationale": "GM demand softening."},
                       {"supplier": "SWKS", "rationale": "Apple momentum intact."}]}))
        d = build_digest(STATE, NOTES)
        self.assertEqual([r["supplier"] for r in d["ranked_open"]], ["AXL", "SWKS"])
        axl = d["ranked_open"][0]
        self.assertEqual(axl["ret"], -0.0210)        # number preserved verbatim from state
        self.assertEqual(axl["rationale"], "GM demand softening.")
        self.assertEqual(d["model_used"], "claude-fable-5")
        self.assertNotIn("watch", d)                 # merged into the ranked list; no separate one

    def test_drops_hallucinated_ticker_and_backfills_missing(self):
        # Model invents NVDA (not open) and forgets AXL -> NVDA dropped, AXL appended with "—".
        self._patch_llm(json.dumps({
            "summary": "",
            "ranked": [{"supplier": "NVDA", "rationale": "not a real open trade"},
                       {"supplier": "SWKS", "rationale": "keep"}]}))
        d = build_digest(STATE, NOTES)
        sups = [r["supplier"] for r in d["ranked_open"]]
        self.assertNotIn("NVDA", sups)
        self.assertEqual(sorted(sups), ["AXL", "SWKS"])   # every real open trade present, once
        axl = next(r for r in d["ranked_open"] if r["supplier"] == "AXL")
        self.assertEqual(axl["rationale"], "—")

    def test_caveat_always_present_even_if_model_omits_it(self):
        self._patch_llm("not even json")
        d = build_digest(STATE, NOTES)
        self.assertEqual(d["caveat"], CAVEAT)
        self.assertEqual(len(d["ranked_open"]), 2)        # both open trades still rendered
        self.assertEqual(d["summary"], "")


class TestFallback(unittest.TestCase):
    def setUp(self):
        self._orig = llm.complete           # save the real client

    def tearDown(self):
        llm.complete = self._orig           # restore (no reload -> class identities stable)

    def test_falls_back_to_opus_on_4xx(self):
        calls = []

        def fake(prompt, model=None, **kw):
            calls.append(model)
            if model == "claude-fable-5":
                raise AnthropicError("Anthropic HTTP 404", code=404)
            return "ok"

        llm.complete = fake
        text, used = llm.complete_fallback("hi")
        self.assertEqual((text, used), ("ok", "claude-opus-4-8"))
        self.assertEqual(calls, ["claude-fable-5", "claude-opus-4-8"])

    def test_primary_used_when_available(self):
        llm.complete = lambda prompt, model=None, **kw: "primary-ok"
        text, used = llm.complete_fallback("hi")
        self.assertEqual((text, used), ("primary-ok", "claude-fable-5"))

    def test_5xx_propagates_without_fallback(self):
        def fake(prompt, model=None, **kw):
            raise AnthropicError("Anthropic HTTP 529", code=529)

        llm.complete = fake
        with self.assertRaises(AnthropicError):
            llm.complete_fallback("hi")


if __name__ == "__main__":
    unittest.main()
