"""Offline unit tests for liquidity primitives (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.liquidity import beta, dollar_adv, is_tradeable  # noqa: E402


def bars(prices, vols, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), float(p), float(v))
            for i, (p, v) in enumerate(zip(prices, vols))]


class TestLiquidity(unittest.TestCase):
    def test_dollar_adv_is_mean_price_times_volume(self):
        b = bars([10, 10, 10], [100, 200, 300])   # 1000, 2000, 3000 -> mean 2000
        self.assertAlmostEqual(dollar_adv(b), 2000.0)

    def test_tradeable_gates_on_price_and_adv(self):
        liquid = bars([50] * 63, [1_000_000] * 63)      # $50M ADV, $50 px
        self.assertTrue(is_tradeable(liquid))
        penny = bars([0.07] * 63, [1_000_000] * 63)     # sub-$5 price
        self.assertFalse(is_tradeable(penny))
        thin = bars([50] * 63, [1000] * 63)             # $50k ADV
        self.assertFalse(is_tradeable(thin))

    def test_beta_of_identical_series_is_one(self):
        rb = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01] * 11   # 66 varying returns
        p = [100.0]
        for r in rb:
            p.append(p[-1] * (1 + r))
        a = bars(p, [1] * len(p))
        self.assertAlmostEqual(beta(a, a), 1.0, places=6)

    def test_beta_of_double_moves_is_two(self):
        rb = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01] * 11
        pb, pa = [100.0], [100.0]
        for r in rb:
            pb.append(pb[-1] * (1 + r))
            pa.append(pa[-1] * (1 + 2 * r))   # a moves exactly 2x b each day
        b = bars(pb, [1] * len(pb))
        a = bars(pa, [1] * len(pa))
        self.assertAlmostEqual(beta(a, b), 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
