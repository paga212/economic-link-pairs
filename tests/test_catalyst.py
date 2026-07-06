"""Offline tests for the News/Catalyst agents (LLM + fetchers monkeypatched)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import elp.catalyst as catalyst  # noqa: E402

IDEA = {"supplier": "GILD", "customer": "CAH", "entry": "2026-06-25"}
HEAD = [{"title": "Cardinal Health raises guidance", "source": "BB", "date": "2026-06-24", "url": ""}]


class TestSourceAgents(unittest.TestCase):
    def tearDown(self):
        catalyst.google_rss = _orig_rss
        catalyst.tiingo_news = _orig_tiingo
        catalyst.complete = _orig_complete

    def test_source_verdict_prompt_includes_headlines_and_parses(self):
        seen = {}

        def fake_complete(prompt, **kw):
            seen["prompt"] = prompt
            return json.dumps({"customer_catalyst": "confirmed", "catalyst_note": "guidance up",
                               "confounding_supplier_news": "no", "confounding_note": "clean"})

        catalyst.complete = fake_complete
        v = catalyst._source_verdict("rss", "CAH", "GILD", HEAD, [])
        self.assertIn("Cardinal Health raises guidance", seen["prompt"])
        self.assertEqual(v["customer_catalyst"], "confirmed")
        self.assertEqual(v["source"], "rss")

    def test_no_headlines_short_circuits_to_unknown_without_calling_llm(self):
        def boom(*a, **k): raise AssertionError("LLM must not be called with no evidence")
        catalyst.complete = boom
        v = catalyst._source_verdict("tiingo", "CAH", "GILD", [], [])
        self.assertEqual(v["customer_catalyst"], "unknown")

    def test_rss_agent_wires_fetch_to_verdict(self):
        catalyst.google_rss = lambda q, days=30: HEAD if q == "CAH" else []
        catalyst.complete = lambda prompt, **kw: json.dumps(
            {"customer_catalyst": "weak", "catalyst_note": "", "confounding_supplier_news": "no",
             "confounding_note": ""})
        self.assertEqual(catalyst.rss_agent(IDEA)["customer_catalyst"], "weak")

    def test_web_agent_degrades_on_unavailable_tool(self):
        def raise_4xx(prompt, **kw): raise catalyst.AnthropicError("HTTP 400", code=400)
        catalyst.complete = raise_4xx
        v = catalyst.web_agent(IDEA)
        self.assertEqual(v["customer_catalyst"], "unknown")
        self.assertIn("web search", v["catalyst_note"].lower())

    def test_source_agent_fail_soft_when_llm_raises(self):
        catalyst.google_rss = lambda q, days=30: [{"title": "x", "source": "s", "date": "", "url": ""}]
        def boom(*a, **k): raise catalyst.AnthropicError("HTTP 500", code=500)
        catalyst.complete = boom
        v = catalyst.rss_agent({"supplier": "GILD", "customer": "CAH"})
        self.assertEqual(v["customer_catalyst"], "unknown")   # degraded, did not raise


class TestMajority(unittest.TestCase):
    def test_majority_and_confounding_are_conservative(self):
        verdicts = [
            {"customer_catalyst": "confirmed", "confounding_supplier_news": "no"},
            {"customer_catalyst": "confirmed", "confounding_supplier_news": "yes"},
            {"customer_catalyst": "unknown", "confounding_supplier_news": "unknown"},
        ]
        m = catalyst._majority(verdicts)
        self.assertEqual(m["customer_catalyst"], "confirmed")   # mode of known verdicts
        self.assertEqual(m["confounding"], "yes")               # any 'yes' -> yes (conservative)

    def test_majority_all_unknown(self):
        m = catalyst._majority([{"customer_catalyst": "unknown"}])
        self.assertEqual(m["customer_catalyst"], "none")
        self.assertEqual(m["confidence"], "low")


_orig_rss = None
_orig_tiingo = None
_orig_complete = None
_orig_assess = None


def setUpModule():
    global _orig_rss, _orig_tiingo, _orig_complete, _orig_assess
    _orig_rss, _orig_tiingo, _orig_complete = catalyst.google_rss, catalyst.tiingo_news, catalyst.complete
    _orig_assess = catalyst.assess_idea


class TestReconcileAndBuild(unittest.TestCase):
    def tearDown(self):
        catalyst.complete = _orig_complete
        catalyst.assess_idea = _orig_assess

    def test_reconcile_parses_master_json(self):
        catalyst.complete = lambda prompt, **kw: json.dumps(
            {"customer_catalyst": "confirmed", "confounding": "no", "confidence": "high",
             "note": "Two sources confirm a guidance raise."})
        out = catalyst.reconcile("CAH", "GILD", [{"customer_catalyst": "confirmed"}])
        self.assertEqual(out["customer_catalyst"], "confirmed")
        self.assertEqual(out["confidence"], "high")

    def test_reconcile_falls_back_to_majority_on_bad_json(self):
        catalyst.complete = lambda prompt, **kw: "not json"
        verdicts = [{"customer_catalyst": "none", "confounding_supplier_news": "no"},
                    {"customer_catalyst": "none", "confounding_supplier_news": "no"}]
        out = catalyst.reconcile("CAH", "GILD", verdicts)
        self.assertEqual(out["customer_catalyst"], "none")   # from _majority

    def test_build_catalyst_keys_every_open_idea(self):
        catalyst.assess_idea = lambda idea: {"customer_catalyst": "weak", "confounding": "no",
                                             "confidence": "med", "note": "x", "sources": []}
        state = {"open": [{"supplier": "GILD", "customer": "CAH"},
                          {"supplier": "PG", "customer": "WMT"}]}
        c = catalyst.build_catalyst(state)
        self.assertEqual(set(c["per_idea"]), {"GILD|CAH", "PG|WMT"})
        self.assertEqual(c["model_used"], catalyst.OPUS)

    def test_catalyst_flag_text(self):
        self.assertIn("confounded", catalyst.catalyst_flag({"confounding": "yes"}))
        self.assertIn("confirmed", catalyst.catalyst_flag({"customer_catalyst": "confirmed",
                                                           "confounding": "no"}))
        self.assertIn("no clear", catalyst.catalyst_flag({"customer_catalyst": "none",
                                                          "confounding": "no"}))
        self.assertEqual(catalyst.catalyst_flag(None), "")


if __name__ == "__main__":
    unittest.main()
