"""Offline unit tests for link validation (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.linkcheck import _price_ok, _name_ok, validate_links  # noqa: E402
from elp.edgar import norm  # noqa: E402


def bars(prices, vol=1_000_000.0, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), float(p), vol) for i, p in enumerate(prices)]


class TestPriceOk(unittest.TestCase):
    def test_clean_liquid_series_ok(self):
        ok, reason = _price_ok(bars([50] * 63))          # $50, $50M ADV
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_empty_series(self):
        self.assertEqual(_price_ok([]), (False, "no_data"))

    def test_penny_or_illiquid(self):
        self.assertEqual(_price_ok(bars([0.07] * 63))[1], "illiquid")   # sub-$5

    def test_glitch_bar_flagged(self):
        # a $0.07 bar among $115 bars -> >5x adjacent jump (the MZTI case)
        px = [115] * 30 + [0.07] + [115] * 32
        self.assertEqual(_price_ok(bars(px))[1], "bad_bars")


class TestNameOk(unittest.TestCase):
    # Stub SEC universe: SNX + Walmart are unique; three "Alpha ..." names make "Alpha" ambiguous.
    T2T = {"SNX": "TD SYNNEX Corporation", "WMT": "Walmart Inc.",
           "ATGL": "Alpha Technology Group Ltd", "AMR": "Alpha Metallurgical Resources Inc",
           "AOSL": "Alpha and Omega Semiconductor Ltd", "APT": "Alpha Pro Tech Ltd"}
    TOKS = [set(norm(t).split()) for t in T2T.values()]

    def test_unambiguous_match_ok(self):
        self.assertEqual(_name_ok("SNX", "TD Synnex Corporation", self.T2T, self.TOKS), (True, ""))
        self.assertEqual(_name_ok("WMT", "Walmart Inc.", self.T2T, self.TOKS), (True, ""))

    def test_generic_name_is_ambiguous(self):     # the NRP->ATGL case
        ok, reason = _name_ok("ATGL", "Alpha", self.T2T, self.TOKS)
        self.assertFalse(ok)
        self.assertEqual(reason, "ambiguous")

    def test_unknown_ticker_specific_name_kept(self):
        # foreign ADR / multi-class ticker absent from the SEC map, but a specific name -> kept
        self.assertEqual(_name_ok("SONY", "Sony Group Corporation", self.T2T, self.TOKS), (True, ""))

    def test_unknown_ticker_ambiguous_still_rejected(self):
        self.assertEqual(_name_ok("ZZZZ", "Alpha", self.T2T, self.TOKS), (False, "ambiguous"))

    def test_name_mismatch(self):
        # ticker exists and raw is specific, but its real title is unrelated
        ok, reason = _name_ok("SNX", "Nvidia Corporation", self.T2T, self.TOKS)
        self.assertEqual((ok, reason), (False, "name_mismatch"))


class TestValidateLinks(unittest.TestCase):
    def _map(self):
        t2t = {"SNX": "TD SYNNEX Corporation", "WMT": "Walmart Inc.", "ADSK": "Autodesk Inc",
               "MZTI": "Mozzarti Inc", "NRP": "Natural Resource Partners LP",
               "ATGL": "Alpha Technology Group Ltd", "AMR": "Alpha Metallurgical Resources Inc",
               "AOSL": "Alpha and Omega Semiconductor Ltd", "APT": "Alpha Pro Tech Ltd"}
        by_cik = {i: {"ticker": tk, "title": ti} for i, (tk, ti) in enumerate(t2t.items())}
        return (by_cik, {})

    def _bars_fn(self, t):
        good = bars([50] * 63)
        glitch = bars([115] * 30 + [0.07] + [115] * 32)   # MZTI glitch
        return {"ADSK": good, "SNX": good, "MZTI": glitch, "WMT": good,
                "NRP": good, "ATGL": good}.get(t, good)

    def test_keeps_good_rejects_bad(self):
        links = [
            {"supplier": "ADSK", "customer": "SNX", "customer_raw": "TD Synnex Corporation"},
            {"supplier": "MZTI", "customer": "WMT", "customer_raw": "Walmart Inc."},   # supplier glitch
            {"supplier": "NRP", "customer": "ATGL", "customer_raw": "Alpha"},           # ambiguous
        ]
        good, rejected = validate_links(links, bars_fn=self._bars_fn, ticker_map=self._map())
        self.assertEqual([g["supplier"] for g in good], ["ADSK"])
        reasons = {r["supplier"]: r["reason"] for r in rejected}
        self.assertEqual(reasons["MZTI"], "supplier_bad_bars")
        self.assertEqual(reasons["NRP"], "ambiguous")


if __name__ == "__main__":
    unittest.main()
