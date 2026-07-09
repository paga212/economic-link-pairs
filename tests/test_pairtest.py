"""Offline unit tests for the Cohen-Frazzini test battery (no network).

Synthetic return dictionaries where the answer is known by construction: a planted lagged
relationship must be found, a pass-through customer must be dropped whatever its statistics
say, and the placebo must reproduce exactly for a given seed.
"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.pairtest import (market_beta, null_summary, placebo, placebo_pvalue,  # noqa: E402
                          pooled_stats, screen, screened_sharpe, suppliers_per_month)


def _months(n: int, y0: int = 2015):
    out, y, m = [], y0, 1
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def _universe(n_pairs: int = 8, n_months: int = 120, lag_beta: float = 0.0, seed: int = 1):
    """Links + returns where each supplier's month-M+1 return loads `lag_beta` on its own
    customer's month-M return. lag_beta=0 is the pure-noise null."""
    rng = random.Random(seed)
    months = _months(n_months)
    links, returns = [], {}
    for i in range(n_pairs):
        s, c = f"S{i}", f"C{i}"
        cust = {m: rng.gauss(0, 0.06) for m in months}
        supp = {m: lag_beta * (cust[months[j - 1]] if j else 0.0) + rng.gauss(0, 0.06)
                for j, m in enumerate(months)}
        returns[c], returns[s] = cust, supp
        links.append((s, c))
    return links, returns


class TestScreen(unittest.TestCase):
    def test_keeps_pairs_with_a_planted_lagged_relationship(self):
        links, returns = _universe(lag_beta=0.8)
        kept, dropped = screen(links, returns)
        self.assertEqual(sorted(kept), sorted(links))
        self.assertEqual(dropped, [])

    def test_drops_pass_through_customer_despite_a_strong_planted_lag(self):
        """Economics beats statistics: the distributor screen runs before any return is read."""
        links, returns = _universe(n_pairs=1, lag_beta=0.9)
        returns["CAH"] = returns.pop("C0")
        kept, dropped = screen([("S0", "CAH")], returns)
        self.assertEqual(kept, [])
        self.assertEqual(dropped, [(("S0", "CAH"), "pass_through_customer")])

    def test_drops_negatively_lagged_pairs(self):
        links, returns = _universe(lag_beta=-0.8)
        kept, dropped = screen(links, returns)
        self.assertEqual(kept, [])
        self.assertTrue(all(r == "lagged_corr<=0" for _, r in dropped))

    def test_drops_short_history(self):
        links, returns = _universe(n_pairs=1, n_months=24, lag_beta=0.8)
        kept, dropped = screen(links, returns)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0][1], "insufficient_history")

    def test_drops_self_links(self):
        _, returns = _universe(n_pairs=1)
        self.assertEqual(screen([("S0", "S0")], returns), ([], [(("S0", "S0"), "self_link")]))

    def test_honours_the_optional_liquidity_gate(self):
        links, returns = _universe(n_pairs=1, lag_beta=0.8)
        kept, dropped = screen(links, returns, tradeable={"S0"})     # C0 missing
        self.assertEqual((kept, dropped), ([], [(("S0", "C0"), "illiquid")]))

    def test_is_pure_and_repeatable(self):
        """placebo() reuses this on rewired universes; it must not mutate or drift."""
        links, returns = _universe(lag_beta=0.5)
        before = {t: dict(r) for t, r in returns.items()}
        first, second = screen(links, returns), screen(links, returns)
        self.assertEqual(first, second)
        self.assertEqual(returns, before)


class TestPooledAndDiagnostics(unittest.TestCase):
    def test_pooled_lagged_corr_is_positive_when_planted(self):
        links, returns = _universe(lag_beta=0.8)
        st = pooled_stats(links, returns)
        self.assertEqual(st["n_pairs"], 8)
        self.assertGreater(st["lagged_corr"], 0.3)
        self.assertGreater(st["up_minus_down"], 0.0)

    def test_pooled_stats_empty_universe(self):
        self.assertEqual(pooled_stats([], {}), {"n_pairs": 0})

    def test_market_beta_recovers_a_planted_slope(self):
        mkt = {m: 0.01 * i for i, m in enumerate(_months(60))}
        series = {m: 1.5 * r for m, r in mkt.items()}
        self.assertAlmostEqual(market_beta(series, mkt), 1.5, places=9)

    def test_market_beta_needs_twelve_common_months(self):
        mkt = {m: 0.01 for m in _months(6)}
        self.assertNotEqual(market_beta(mkt, mkt), market_beta(mkt, mkt))    # NaN

    def test_suppliers_per_month_counts_the_cross_section(self):
        links, returns = _universe(n_pairs=3, n_months=40)
        counts = suppliers_per_month(links, returns)
        self.assertEqual(max(counts.values()), 3)       # all three priced in a full month
        self.assertEqual(min(counts.values()), 0)       # first month has no prior-month signal


class TestPlacebo(unittest.TestCase):
    def test_is_deterministic_for_a_given_seed(self):
        links, returns = _universe(lag_beta=0.4)
        a = placebo(links, returns, n=50, seed=7)
        b = placebo(links, returns, n=50, seed=7)
        self.assertEqual(a, b)
        self.assertNotEqual(a, placebo(links, returns, n=50, seed=8))

    def test_null_mean_is_positive_under_pure_noise(self):
        """The screen keeps only lagged_corr>0 pairs, so even a RANDOM rewiring of pure noise
        produces a positive Sharpe. This is the data-snooping bias made visible, and it is the
        entire reason the real statistic must be compared against a screened null rather than
        against zero."""
        links, returns = _universe(n_pairs=8, lag_beta=0.0, seed=3)
        null = placebo(links, returns, n=200, seed=0)
        self.assertGreater(len(null), 100)
        self.assertGreater(null_summary(null)["mean"], 0.0)

    def test_a_planted_link_beats_its_own_placebo(self):
        """Power check: when the wiring genuinely carries the signal, the real Sharpe must sit
        far out in the tail of the rewired null."""
        links, returns = _universe(n_pairs=8, lag_beta=0.8, seed=5)
        real = screened_sharpe(links, returns)
        null = placebo(links, returns, n=200, seed=0)
        self.assertIsNotNone(real)
        self.assertLessEqual(placebo_pvalue(real, null), 0.05)

    def test_pvalue_is_add_one_corrected(self):
        self.assertEqual(placebo_pvalue(999.0, [1.0, 2.0, 3.0]), 0.25)   # never an exact zero
        self.assertEqual(placebo_pvalue(0.0, [1.0, 2.0, 3.0]), 1.0)

    def test_null_summary_on_empty(self):
        self.assertEqual(null_summary([]), {"n": 0})


class TestScreenedSharpe(unittest.TestCase):
    def test_none_when_the_screen_empties_the_universe(self):
        links, returns = _universe(lag_beta=-0.8)         # every pair fails lagged_corr>0
        self.assertIsNone(screened_sharpe(links, returns))

    def test_none_when_a_single_link_survives(self):
        links, returns = _universe(n_pairs=1, lag_beta=0.8)
        self.assertIsNone(screened_sharpe(links, returns))   # no cross-section to rank


if __name__ == "__main__":
    unittest.main()
