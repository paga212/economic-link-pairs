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
        """Smoke test only: checks the static and PIT code paths agree when the PIT
        table repeats the same links every month. Because the content never varies
        by month, this does NOT distinguish formation-month indexing from
        holding-month indexing (both would produce identical output here); the
        formation/holding key-swap guard lives in
        test_a_formation_holding_key_swap_is_detected below."""
        R = self._returns()
        static = [("S1", "C1"), ("S2", "C2")]
        pit = {m: list(static) for m in _months(6)}
        self.assertEqual(long_short_returns(static, R), long_short_returns(pit, R))

    def test_a_formation_holding_key_swap_is_detected(self):
        """PIT link content varies from month to month, so indexing by holding month
        (a formation<->holding key-swap bug) selects a genuinely different supplier
        set than indexing by formation month, and yields a different long-short
        return -- not merely a plausible-looking one."""
        months = _months(8)
        mapping_a = [("S1", "C1"), ("S2", "C2"), ("S3", "C3")]
        mapping_b = [("S1", "C3"), ("S2", "C2"), ("S3", "C1")]  # C1/C3 swapped vs S1/S3
        links = {m: (mapping_a if i % 2 == 0 else mapping_b) for i, m in enumerate(months)}

        returns = {
            "C1": {m: 0.10 for m in months},
            "C2": {m: 0.00 for m in months},
            "C3": {m: -0.10 for m in months},
            "S1": {m: 1.0 for m in months},
            "S2": {m: 2.0 for m in months},
            "S3": {m: 3.0 for m in months},
        }

        H = months[4]  # interior holding month: not first/last, so neither a
        # KeyError nor the n<2 filter can mask the bug. Formation month is
        # months[3] (odd index -> mapping_b); H itself is even index -> mapping_a.
        # Adjacent months always have opposite parity, so the two mappings never
        # coincide between a formation month and its holding month.

        out = long_short_returns(links, returns)

        # Correct (formation-keyed) result: cust_of(links[months[3]]) = mapping_b ->
        # S1->C3 (rc=-0.10), S2->C2 (rc=0.00), S3->C1 (rc=0.10)
        # ranked ascending by rc: S1, S2, S3 -> short S1, long S3
        # ls = supplier_holding(S3) - supplier_holding(S1) = 3.0 - 1.0 = 2.0
        expected_from_formation = 2.0

        # If the engine instead indexed the PIT dict by holding month H directly,
        # it would use cust_of(links[H]) = mapping_a ->
        # S1->C1 (rc=0.10), S2->C2 (rc=0.00), S3->C3 (rc=-0.10)
        # ranked ascending by rc: S3, S2, S1 -> short S3, long S1
        # ls = supplier_holding(S1) - supplier_holding(S3) = 1.0 - 3.0 = -2.0
        expected_from_holding = -2.0

        self.assertIn(H, out)
        self.assertAlmostEqual(out[H], expected_from_formation, places=9)
        self.assertNotAlmostEqual(out[H], expected_from_holding, places=9)

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
