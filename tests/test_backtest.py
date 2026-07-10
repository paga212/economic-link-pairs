"""Offline unit tests for the backtest engine (no network, deterministic)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.backtest import long_short_returns, performance, signal_ranking  # noqa: E402


def _months(n, start=(2020, 1)):
    y, m = start
    out = []
    for _ in range(n):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class TestBacktest(unittest.TestCase):
    def _perfect_leadlag(self):
        """3 suppliers with distinct customers; supplier month-(M+1) return == customer
        month-M return. So ranking by customer prior return perfectly orders supplier
        holding return, and long-short each month = top customer sig minus bottom."""
        keys = _months(15)
        cust_sig = {  # per month, three distinct customer returns
            k: {"C1": 0.02 + 0.001 * i, "C2": -0.01 + 0.001 * i, "C3": 0.05 - 0.001 * i}
            for i, k in enumerate(keys)
        }
        returns = {"C1": {}, "C2": {}, "C3": {}, "S1": {}, "S2": {}, "S3": {}}
        for i, k in enumerate(keys):
            for c in ("C1", "C2", "C3"):
                returns[c][k] = cust_sig[k][c]
            if i + 1 < len(keys):
                nxt = keys[i + 1]
                returns["S1"][nxt] = cust_sig[k]["C1"]
                returns["S2"][nxt] = cust_sig[k]["C2"]
                returns["S3"][nxt] = cust_sig[k]["C3"]
        links = [("S1", "C1"), ("S2", "C2"), ("S3", "C3")]
        return links, returns, cust_sig, keys

    def test_direction_and_magnitude(self):
        links, returns, cust_sig, keys = self._perfect_leadlag()
        series = long_short_returns(links, returns, side_frac=0.34)  # k=1 of 3 -> top/bottom
        self.assertGreater(len(series), 5)
        for H, ls in series.items():
            self.assertGreater(ls, 0)  # long-short positive every month by construction
        # each month LS == (max customer sig - min customer sig) in the formation month
        H = sorted(series)[0]
        M = keys[keys.index(H) - 1]
        sigs = list(cust_sig[M].values())
        self.assertAlmostEqual(series[H], max(sigs) - min(sigs), places=9)

    def test_reproducible(self):
        links, returns, *_ = self._perfect_leadlag()
        self.assertEqual(long_short_returns(links, returns),
                         long_short_returns(links, returns))

    def test_cost_reduces_return_linearly(self):
        links, returns, *_ = self._perfect_leadlag()
        gross = long_short_returns(links, returns, cost_bps=0.0)
        net = long_short_returns(links, returns, cost_bps=10.0)
        for H in gross:
            self.assertAlmostEqual(gross[H] - net[H], 2 * 10.0 / 1e4, places=12)

    def test_performance_stats(self):
        p = performance({(2020, 1): 0.01, (2020, 2): -0.01, (2020, 3): 0.03})
        self.assertEqual(p["n"], 3)
        self.assertAlmostEqual(p["mean_monthly"], 0.01, places=9)
        self.assertAlmostEqual(p["hit_rate"], 2 / 3, places=9)

    def test_signal_ranking_orders_by_customer_return(self):
        returns = {"C1": {(2020, 1): 0.05}, "C2": {(2020, 1): -0.02},
                   "C3": {(2020, 1): 0.01}, "S1": {}, "S2": {}, "S3": {}}
        r = signal_ranking([("S1", "C1"), ("S2", "C2"), ("S3", "C3")], returns, (2020, 1))
        self.assertEqual([s for s, _, _ in r], ["S1", "S3", "S2"])  # desc by customer return
        # supplier whose customer has no return that month is dropped
        r2 = signal_ranking([("S1", "C1"), ("S9", "CX")], returns, (2020, 1))
        self.assertEqual([s for s, _, _ in r2], ["S1"])

    def test_needs_two_names(self):
        # single supplier -> no cross-section -> no months
        returns = {"C1": {(2020, 1): 0.05}, "S1": {(2020, 2): 0.05}}
        self.assertEqual(long_short_returns([("S1", "C1")], returns), {})


class TestPointInTimeLinks(unittest.TestCase):
    def _returns(self):
        ms = _months(6)
        return {"S1": {m: 0.01 * i for i, m in enumerate(ms)},
                "S2": {m: -0.01 * i for i, m in enumerate(ms)},
                "C1": {m: 0.05 for m in ms},
                "C2": {m: -0.05 for m in ms}}

    def test_a_repeated_mapping_equals_the_static_list(self):
        """A per-month table that repeats the same links must reproduce the static result."""
        R = self._returns()
        static = [("S1", "C1"), ("S2", "C2")]
        pit = {m: list(static) for m in _months(6)}
        self.assertEqual(long_short_returns(static, R), long_short_returns(pit, R))

    def test_a_month_with_no_links_is_skipped(self):
        R = self._returns()
        pit = {m: [] for m in _months(6)}
        self.assertEqual(long_short_returns(pit, R), {})

    def test_links_absent_in_a_formation_month_do_not_trade_it(self):
        R = self._returns()
        ms = _months(6)
        pit = {m: ([("S1", "C1"), ("S2", "C2")] if i >= 3 else []) for i, m in enumerate(ms)}
        out = long_short_returns(pit, R)
        # formation month ms[i] drives holding month ms[i+1]
        self.assertNotIn(ms[1], out)
        self.assertIn(ms[4], out)


if __name__ == "__main__":
    unittest.main()
