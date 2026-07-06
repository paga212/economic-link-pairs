"""Offline render check for the dashboard idea row (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard import idea_row  # noqa: E402

IDEA = {"supplier": "SWKS", "customer": "AAPL", "side": -1, "expression": "stock-pair",
        "entry": "2026-06-01", "days": 8, "ret": 0.012, "stop": -0.05, "risk_cap": "soft",
        "primary": {"role": "primary", "ticker": "SWKS", "direction": -1, "instrument": "spread",
                    "notional": 200000.0, "entry_px": 143.06, "S0": 143.06,
                    "k_long": 143.0, "k_short": 129.0, "debit": 3.6, "dte": 45},
        "neutralizer": {"role": "neutralizer", "ticker": "QRVO", "direction": 1, "instrument": "stock",
                        "notional": 200000.0, "entry_px": 95.0}}


class TestIdeaRow(unittest.TestCase):
    def test_row_states_direction_legs_and_expression(self):
        html = idea_row(IDEA)
        self.assertIn("SHORT SWKS", html)          # net direction in plain English
        self.assertIn("AAPL", html)                # driving customer
        self.assertIn("QRVO", html)                # neutralizing leg
        self.assertIn("stock-pair", html)          # expression tag
        self.assertIn("143", html)                 # snapped strike shown
        self.assertIn("+1.2%", html)                # net return from state, not a model

    def test_row_shows_catalyst_flag_when_supplied(self):
        html = idea_row(IDEA, {"customer_catalyst": "none", "confounding": "yes"})
        self.assertIn("confounded", html)

    def test_row_shows_risk_flag_when_supplied(self):
        html = idea_row(IDEA, None, {"borrow": {"class": "hard"}})
        self.assertIn("hard to borrow", html)


class TestScorecardPanel(unittest.TestCase):
    def test_panel_shows_verdict_and_metrics(self):
        from dashboard import _scorecard_html
        sc = {"verdict": "PENDING", "months": 0.1, "n_closed": 0,
              "sharpe": None, "expectancy": None, "ideas_per_month": None,
              "sharpe_ok": False, "expectancy_ok": False, "volume_ok": False}
        html = _scorecard_html(sc)
        self.assertIn("Kill-rule scorecard", html)
        self.assertIn("PENDING", html)
        self.assertIn("net Sharpe", html)
        self.assertIn("0/30", html)          # gate progress


class TestDashboardLink(unittest.TestCase):
    def test_index_links_to_trades_page(self):
        import dashboard, json, os, shutil
        cwd = os.getcwd(); tmp = os.path.join(os.path.dirname(__file__), "_dashtmp")
        os.makedirs(tmp, exist_ok=True); os.chdir(tmp)
        try:
            json.dump({"generated_utc": "t", "start": "2026-07-04", "open": [], "closed": [],
                       "stats": {}}, open("paper_state.json", "w"))
            dashboard.build()
            self.assertIn("trades.html", open("site/index.html").read())
        finally:
            os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)
