"""Offline unit tests for the point-in-time link table (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.pit import LIFE_MONTHS, links_asof  # noqa: E402


def _months(n, y0=2020, m0=1):
    out, y, m = [], y0, m0
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


LINK = [{"supplier": "S", "customer": "C", "filed": "2020-03-15"}]


class TestLinksAsof(unittest.TestCase):
    def test_link_is_absent_before_and_during_its_filing_month(self):
        t = links_asof(LINK, _months(6))
        self.assertEqual(t[(2020, 2)], [])
        self.assertEqual(t[(2020, 3)], [])     # not tradeable the month it was filed

    def test_link_is_live_the_month_after_filing(self):
        t = links_asof(LINK, _months(6))
        self.assertEqual(t[(2020, 4)], [("S", "C")])

    def test_link_lapses_exactly_life_months_after_filing(self):
        t = links_asof(LINK, _months(30))
        last = (2021, 3 + LIFE_MONTHS - 12)     # 2020-03 + 15 months = 2021-06
        self.assertEqual(t[last], [("S", "C")])
        y, m = last
        nxt = (y, m + 1) if m < 12 else (y + 1, 1)
        self.assertEqual(t[nxt], [])

    def test_a_refiling_extends_the_link(self):
        dated = LINK + [{"supplier": "S", "customer": "C", "filed": "2021-03-10"}]
        t = links_asof(dated, _months(30))
        self.assertEqual(t[(2022, 1)], [("S", "C")])     # covered by the 2021 filing

    def test_every_requested_month_is_a_key(self):
        t = links_asof(LINK, _months(6))
        self.assertEqual(sorted(t), sorted(_months(6)))

    def test_no_duplicate_pairs_within_a_month(self):
        dated = LINK + [{"supplier": "S", "customer": "C", "filed": "2020-03-20"}]
        self.assertEqual(links_asof(dated, _months(6))[(2020, 4)], [("S", "C")])

    def test_result_is_sorted_and_deterministic(self):
        dated = [{"supplier": "Z", "customer": "A", "filed": "2020-01-05"},
                 {"supplier": "A", "customer": "B", "filed": "2020-01-05"}]
        self.assertEqual(links_asof(dated, _months(3))[(2020, 2)], [("A", "B"), ("Z", "A")])


if __name__ == "__main__":
    unittest.main()
