"""Offline test: the tradeviz.py entry writes site/trades.html and fails soft."""
import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tradeviz as entry  # noqa: E402

IDEA = {"supplier": "GILD", "customer": "CAH", "side": 1, "expression": "stock-pair",
        "entry": "2026-06-02",
        "primary": {"role": "primary", "ticker": "GILD", "direction": 1, "instrument": "stock",
                    "notional": 200000.0, "entry_px": 100.0},
        "neutralizer": {"role": "neutralizer", "ticker": "VC", "direction": -1, "instrument": "stock",
                        "notional": 200000.0, "entry_px": 50.0}}
BARS = {"GILD": [(date(2026, 6, 1), 90.0, 1e6), (date(2026, 6, 2), 100.0, 1e6)],
        "VC": [(date(2026, 6, 1), 50.0, 1e6), (date(2026, 6, 2), 50.0, 1e6)]}


class TestEntry(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = os.path.join(os.path.dirname(__file__), "_tvtmp")
        os.makedirs(self._tmp, exist_ok=True)
        os.chdir(self._tmp)
        entry.fetch_daily_bars = lambda t, start=None: BARS.get(t, [])

    def tearDown(self):
        import shutil
        entry.fetch_daily_bars = _ORIG
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_writes_trades_html(self):
        json.dump({"open": [IDEA]}, open("paper_state.json", "w"))
        entry.build()
        self.assertTrue(os.path.exists("site/trades.html"))
        self.assertIn("LONG GILD", open("site/trades.html").read())

    def test_no_state_still_writes_page(self):
        entry.build()                                 # no paper_state.json -> fail soft
        self.assertTrue(os.path.exists("site/trades.html"))
        self.assertIn("No open trades", open("site/trades.html").read())

    def test_fetch_error_is_fail_soft(self):
        json.dump({"open": [IDEA]}, open("paper_state.json", "w"))
        def boom(t, start=None): raise RuntimeError("net down")
        entry.fetch_daily_bars = boom
        entry.build()                                 # must not raise
        self.assertTrue(os.path.exists("site/trades.html"))

    def test_corrupt_state_is_fail_soft(self):
        open("paper_state.json", "w").write("not json{")
        entry.build()                          # must not raise
        self.assertTrue(os.path.exists("site/trades.html"))


_ORIG = entry.fetch_daily_bars


if __name__ == "__main__":
    unittest.main()
