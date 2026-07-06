"""Offline unit tests for the weekly email report (no network, no SMTP)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_report import render  # noqa: E402

STATE = {
    "generated_utc": "2026-07-05T16:00:00+00:00", "start": "2026-07-04",
    "open": [
        {"supplier": "GILD", "customer": "CAH", "side": 1, "expression": "stock-pair",
         "entry": "2026-06-25", "days": 7, "ret": 0.06, "stop": 0.01, "risk_cap": "soft",
         "primary": {"role": "primary", "ticker": "GILD", "direction": 1, "instrument": "stock",
                     "notional": 200000.0, "entry_px": 123.84},
         "neutralizer": {"role": "neutralizer", "ticker": "VC", "direction": -1,
                         "instrument": "stock", "notional": 200000.0, "entry_px": 102.45}},
        {"supplier": "PG", "customer": "WMT", "side": -1, "expression": "stock-hedge",
         "entry": "2026-07-01", "days": 1, "ret": -0.009, "stop": -0.05, "risk_cap": "soft",
         "primary": {"role": "primary", "ticker": "PG", "direction": -1, "instrument": "spread",
                     "notional": 200000.0, "entry_px": 147.4, "k_long": 147.0, "k_short": 133.0,
                     "debit": 3.60, "dte": 45},
         "neutralizer": {"role": "neutralizer", "ticker": "SPY", "direction": 1,
                         "instrument": "stock", "notional": 60000.0, "entry_px": 744.78}},
    ],
    "closed": [], "stats": {"n": 0, "win_rate": None, "mean_ret": None},
}


class TestRender(unittest.TestCase):
    def test_html_and_text_contain_the_ideas(self):
        html, text = render(STATE, None)
        for blob in (html, text):
            self.assertIn("GILD", blob)
            self.assertIn("PG", blob)
            self.assertIn("stock-hedge", blob)          # expression
            self.assertIn("buy 147P", blob)             # spread: long the higher-strike put
            self.assertIn("sell 133P", blob)            # spread: short the lower-strike put
            self.assertIn("exp 45d", blob)              # DTE spelled out, not "45DTE"
            self.assertIn("1,615 sh", blob)             # exact share count on the long leg
            self.assertIn("recommendations only", blob.lower())   # caveat
            self.assertIn("100.103.143.120:8787", blob)          # dashboard link
        self.assertIn("+6.0%", html)                    # net from state
        self.assertIn("$60k", html)                     # clamped hedge notional

    def test_digest_included_only_when_present(self):
        html_no, _ = render(STATE, None)
        self.assertNotIn("Daily read", html_no)
        html_yes, _ = render(STATE, {"model_used": "claude-fable-5", "summary": "Book looks fine."})
        self.assertIn("Daily read", html_yes)
        self.assertIn("Book looks fine.", html_yes)

    def test_catalyst_flag_appears_when_catalyst_json_present(self):
        import email_report, json, os
        cwd = os.getcwd(); tmp = os.path.join(os.path.dirname(__file__), "_emailcat")
        os.makedirs(tmp, exist_ok=True); os.chdir(tmp)
        try:
            json.dump({"per_idea": {"GILD|CAH": {"customer_catalyst": "confirmed",
                       "confounding": "no"}}}, open("catalyst.json", "w"))
            html, text = email_report.render(STATE, None)
            self.assertIn("catalyst: confirmed", html)
        finally:
            os.chdir(cwd)
            import shutil; shutil.rmtree(tmp, ignore_errors=True)


import email_report  # noqa: E402


class TestSend(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = os.path.join(os.path.dirname(__file__), "_emailtmp")
        os.makedirs(self._tmp, exist_ok=True)
        os.chdir(self._tmp)

    def tearDown(self):
        import shutil
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_dryrun_writes_eml_and_never_connects(self):
        # Poison smtplib so any socket attempt fails loudly; dry-run must not touch it.
        orig = email_report.smtplib.SMTP
        email_report.smtplib.SMTP = lambda *a, **k: (_ for _ in ()).throw(AssertionError("connected!"))
        try:
            email_report.send("<b>hi</b>", "hi", dryrun=True)
        finally:
            email_report.smtplib.SMTP = orig
        self.assertTrue(os.path.exists(email_report.EML_FILE))
        body = open(email_report.EML_FILE).read()
        self.assertIn(email_report.TO, body)
        self.assertIn("hi", body)

    def test_password_prefers_env_then_errors(self):
        os.environ["GMAIL_APP_PASSWORD"] = "abcd efgh ijkl mnop"
        try:
            self.assertEqual(email_report._password(), "abcd efgh ijkl mnop")
        finally:
            del os.environ["GMAIL_APP_PASSWORD"]
        # no env, no file in this tmp cwd, and force HOME miss -> RuntimeError
        home = os.environ.get("HOME")
        os.environ["HOME"] = self._tmp
        try:
            with self.assertRaises(RuntimeError):
                email_report._password()
        finally:
            if home is not None:
                os.environ["HOME"] = home


if __name__ == "__main__":
    unittest.main()
