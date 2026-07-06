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
