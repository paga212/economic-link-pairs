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


class TestSupersession(unittest.TestCase):
    """A supplier can have several live links at once (10-Qs file quarterly against a
    ~12-month refiling cadence, and LIFE_MONTHS=15 bridges slips). The most recent filing
    is the point-in-time truth; older, still-live filings for the same supplier must not
    also appear."""

    def test_a_newer_filing_supersedes_an_older_one_for_the_same_supplier(self):
        # customer "Z" (alphabetically LATER than "A") is the newer, correct filing -- a
        # regression to sorted-first would report "A" instead and this must fail.
        dated = [{"supplier": "S", "customer": "A", "filed": "2020-03-15"},
                 {"supplier": "S", "customer": "Z", "filed": "2020-06-15"}]
        t = links_asof(dated, _months(20))
        # "A" live 2020-04..2021-06, "Z" live 2020-07..2021-09: 2020-08 is in both windows.
        self.assertEqual(t[(2020, 8)], [("S", "Z")])

    def test_the_newer_filing_remains_the_only_one_once_the_older_lapses(self):
        dated = [{"supplier": "S", "customer": "A", "filed": "2020-03-15"},
                 {"supplier": "S", "customer": "Z", "filed": "2020-06-15"}]
        t = links_asof(dated, _months(30))
        # "A" lapses after 2021-06; "Z" is still live (until 2021-09).
        self.assertEqual(t[(2021, 7)], [("S", "Z")])

    def test_a_supplier_with_a_single_link_is_unaffected(self):
        dated = LINK + [{"supplier": "T", "customer": "D", "filed": "2020-03-15"}]
        t = links_asof(dated, _months(6))
        self.assertEqual(t[(2020, 4)], [("S", "C"), ("T", "D")])

    def test_same_day_tie_falls_back_to_the_alphabetically_first_customer(self):
        dated = [{"supplier": "S", "customer": "Z", "filed": "2020-03-15"},
                 {"supplier": "S", "customer": "A", "filed": "2020-03-15"}]
        t = links_asof(dated, _months(6))
        self.assertEqual(t[(2020, 4)], [("S", "A")])


if __name__ == "__main__":
    unittest.main()
