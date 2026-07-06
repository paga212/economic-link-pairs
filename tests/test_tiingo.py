"""Offline unit tests for Tiingo row parsing (no network)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.tiingo import _parse_bars  # noqa: E402
import elp.tiingo as _tiingo  # noqa: E402


class TestParseBars(unittest.TestCase):
    def test_parses_date_close_volume(self):
        rows = [{"date": "2020-01-02T00:00:00.000Z", "adjClose": 100.0, "adjVolume": 1_000_000},
                {"date": "2020-01-03T00:00:00.000Z", "adjClose": 101.0, "adjVolume": 2_000_000}]
        out = _parse_bars(rows)
        self.assertEqual(out[0], (date(2020, 1, 2), 100.0, 1_000_000.0))
        self.assertEqual(out[1][2], 2_000_000.0)

    def test_falls_back_to_raw_volume(self):
        rows = [{"date": "2020-01-02T00:00:00.000Z", "adjClose": 50.0, "volume": 500_000}]
        self.assertEqual(_parse_bars(rows)[0], (date(2020, 1, 2), 50.0, 500_000.0))


class TestFundamentals(unittest.TestCase):
    def tearDown(self):
        _tiingo._fetch = _ORIG_FETCH

    def test_marketcap_takes_latest_nonzero(self):
        _tiingo._fetch = lambda url, sym: [
            {"date": "2026-06-01", "marketCap": 100.0}, {"date": "2026-07-01", "marketCap": 250.0}]
        self.assertEqual(_tiingo.fetch_marketcap("AMGN"), 250.0)

    def test_statement_dates_sorted_unique(self):
        _tiingo._fetch = lambda url, sym: [
            {"date": "2026-03-31T00:00:00.000Z"}, {"date": "2025-12-31T00:00:00.000Z"},
            {"date": "2025-12-31T00:00:00.000Z"}]
        self.assertEqual(_tiingo.fetch_statement_dates("AMGN"), ["2025-12-31", "2026-03-31"])

    def test_fetch_error_fails_soft(self):
        def boom(url, sym): raise RuntimeError("Tiingo HTTP 403")
        _tiingo._fetch = boom
        self.assertIsNone(_tiingo.fetch_marketcap("X"))
        self.assertEqual(_tiingo.fetch_statement_dates("X"), [])


_ORIG_FETCH = None


def setUpModule():
    global _ORIG_FETCH
    _ORIG_FETCH = _tiingo._fetch


if __name__ == "__main__":
    unittest.main()
