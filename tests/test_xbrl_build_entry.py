"""Offline test: the xbrl_build.py entry dedupes/sorts/filters and writes JSON. No network.

Also proves the principal-customer fix: for a (supplier, filed) filing that discloses
more than one customer, xbrl_build.py must emit only the customer with the largest
disclosed USD revenue, not the alphabetically-first one.
"""
import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xbrl_build as entry  # noqa: E402

REVENUE_TAG = "RevenueFromContractWithCustomerExcludingAssessedTax"

BY_CIK = {1: {"ticker": "ICHR", "title": "Ichor Holdings"},
          2: {"ticker": "LRCX", "title": "Lam Research"},
          3: {"ticker": "DAN", "title": "Dana Inc"},
          4: {"ticker": "SELF", "title": "Self Supplier Corp"},
          5: {"ticker": "ZOO", "title": "Zoo Corp"},
          6: {"ticker": "ABC", "title": "Abc Corp"},
          7: {"ticker": "RANK", "title": "Rank Corp"},
          8: {"ticker": "DECOY1", "title": "Decoy1 Corp"},
          9: {"ticker": "DECOY2", "title": "Decoy2 Corp"},
          10: {"ticker": "FBK", "title": "Fallback Corp"},
          11: {"ticker": "TAGSUP", "title": "Tag Supplier Corp"},
          12: {"ticker": "MAXSUP", "title": "Max Supplier Corp"}}
BY_NAME = {}
TITLES = {}


def _row(cik, member, filed, value, tag="", uom=""):
    return {"cik": cik, "member": member, "filed": filed, "value": value, "tag": tag, "uom": uom}


# rows keyed by quarter; each row matches elp.fsds.major_customers()'s output shape:
# {cik, member, filed, value, tag, uom}.
# 1999q1 rows are deliberately ordered so that, absent the explicit `links.sort(...)` in
# xbrl_build.main(), the output would NOT come out in (filed, supplier, customer) order:
#   - ZOO files before ABC on the same filed date (out of alphabetical `supplier` order)
ROWS_BY_Q = {
    "1999q1": [
        # resolves to LRCX -> a real link, appears twice (dup filed date) -> dedup to 1
        _row(1, "LamResearchMember", date(1999, 2, 1), 1e6, REVENUE_TAG, "USD"),
        _row(1, "LamResearchMember", date(1999, 2, 1), 1e6, REVENUE_TAG, "USD"),
        # unresolvable member -> dropped
        _row(1, "OtherMember", date(1999, 2, 1), 5e5, REVENUE_TAG, "USD"),
        # self-link -> dropped (customer resolves to same ticker as supplier)
        _row(4, "SelfSupplierCorpMember", date(1999, 2, 1), 1e5, REVENUE_TAG, "USD"),
        # ZOO<-LRCX arrives BEFORE ABC<-LRCX, same filed date: out of alphabetical supplier order
        _row(5, "LamResearchMember", date(1999, 2, 1), 3e5, REVENUE_TAG, "USD"),
        _row(6, "LamResearchMember", date(1999, 2, 1), 3e5, REVENUE_TAG, "USD"),

        # --- principal-customer selection scenarios (Change 2) ---

        # RANK files a filing with two customers, USD revenue rows differ. The larger,
        # ZZZCORP, is alphabetically LATER than AAACORP: if the code regressed to
        # sorted(customers)[0], it would wrongly pick AAACORP.
        _row(7, "AaaCorpMember", date(1999, 2, 15), 1e6, REVENUE_TAG, "USD"),
        _row(7, "ZzzCorpMember", date(1999, 2, 15), 5e6, REVENUE_TAG, "USD"),

        # DECOY1: a non-revenue tag (AccountsReceivableNetCurrent) with a huge value must
        # not beat a small but genuine USD revenue row.
        _row(8, "HugeArMember", date(1999, 2, 20), 9e9, "AccountsReceivableNetCurrent", "USD"),
        _row(8, "SmallRevMember", date(1999, 2, 20), 1e5, REVENUE_TAG, "USD"),

        # DECOY2: a non-USD row with a huge value must not beat a small USD revenue row.
        _row(9, "HugeEurMember", date(1999, 2, 25), 9e9, REVENUE_TAG, "EUR"),
        _row(9, "SmallUsdMember", date(1999, 2, 25), 2e5, REVENUE_TAG, "USD"),

        # FBK: no rankable rows at all (no USD revenue tag anywhere) -> falls back to the
        # alphabetically-first customer (BbbMember -> BBB) and is still emitted.
        _row(10, "YyyMember", date(1999, 3, 1), None, "", ""),
        _row(10, "BbbMember", date(1999, 3, 1), None, "", ""),

        # TAGSUP: pre-ASC 606 revenue-tag coverage (Bug 1). ZZZ is tagged SalesRevenueNet
        # ($900), AAA is tagged Revenues ($100). ZZZ must win. Under the old
        # startswith("revenue") predicate, "salesrevenuenet" does not start with
        # "revenue", so ZZZ's row would not rank and AAA (the only rankable row) would
        # wrongly win.
        _row(11, "ZzzSalesMember", date(1999, 4, 1), 900, "SalesRevenueNet", "USD"),
        _row(11, "AaaRevMember", date(1999, 4, 1), 100, "Revenues", "USD"),

        # MAXSUP: MAX not SUM (Bug 2). AAA has three rankable rows of 100 each (same
        # member, repeated tagging across contexts -- sum 300, max 100). ZZZ has one
        # rankable row of 200 (max 200). ZZZ must win: 200 > 100. Under a SUM
        # aggregation AAA would wrongly win with 300.
        _row(12, "AaaMaxMember", date(1999, 4, 5), 100, REVENUE_TAG, "USD"),
        _row(12, "AaaMaxMember", date(1999, 4, 5), 100, REVENUE_TAG, "USD"),
        _row(12, "AaaMaxMember", date(1999, 4, 5), 100, REVENUE_TAG, "USD"),
        _row(12, "ZzzMaxMember", date(1999, 4, 5), 200, REVENUE_TAG, "USD"),
    ],
    "1999q2": [
        # a second, later disclosure of the same DAN link
        _row(3, "LamResearchMember", date(1999, 5, 1), 2e6, REVENUE_TAG, "USD"),
    ],
}


def fake_fetch_quarter(q, dest):
    open(dest, "w").write("fake")
    return dest


def fake_major_customers(zip_path):
    # zip_path basename is "fsds_<pid>_<q>.zip" (or "fsds_<q>.zip" pre-Fix1); the quarter
    # itself never contains "_", so the last underscore-separated segment is always it.
    base = os.path.basename(zip_path)
    q = base.removeprefix("fsds_").removesuffix(".zip").rsplit("_", 1)[-1]
    return ROWS_BY_Q.get(q, [])


def fake_resolve_member(member, by_name, titles):
    return {
        "LamResearchMember": "LRCX",
        "SelfSupplierCorpMember": "SELF",
        "AaaCorpMember": "AAACORP",
        "ZzzCorpMember": "ZZZCORP",
        "HugeArMember": "AAAHUGE",
        "SmallRevMember": "SMALLREV",
        "HugeEurMember": "AAAEUR",
        "SmallUsdMember": "SMALLUSD",
        "YyyMember": "YYY",
        "BbbMember": "BBB",
        "ZzzSalesMember": "ZZZ",
        "AaaRevMember": "AAA",
        "AaaMaxMember": "AAA",
        "ZzzMaxMember": "ZZZ",
    }.get(member)


class TestEntry(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = os.path.join(os.path.dirname(__file__), "_xbtmp")
        os.makedirs(self._tmp, exist_ok=True)
        os.chdir(self._tmp)
        entry.load_ticker_map = lambda: (BY_CIK, BY_NAME)
        entry.title_index = lambda by_cik: TITLES
        entry.fetch_quarter = fake_fetch_quarter
        entry.major_customers = fake_major_customers
        entry.resolve_member = fake_resolve_member

    def tearDown(self):
        import shutil
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_writes_deduped_sorted_filtered_links(self):
        out = "xbrl_links_test.json"
        entry.main("1999q1", "1999q2", out=out)
        self.assertTrue(os.path.exists(out))
        links = json.load(open(out))

        # self-link (SELF<-SELF) and unresolvable (OtherMember) must be dropped
        for x in links:
            self.assertNotEqual(x["supplier"], x["customer"])
        self.assertEqual({frozenset(x.keys()) for x in links}, {frozenset({"supplier", "customer", "filed"})})

        # dedup on (supplier, customer, filed): the duplicate 1999q1 LRCX row collapses to one
        keys = [(x["supplier"], x["customer"], x["filed"]) for x in links]
        self.assertEqual(len(keys), len(set(keys)))

        # exactly the links below survive
        self.assertEqual(sorted((x["supplier"], x["customer"], x["filed"]) for x in links),
                          [("ABC", "LRCX", "1999-02-01"),
                           ("DAN", "LRCX", "1999-05-01"),
                           ("DECOY1", "SMALLREV", "1999-02-20"),
                           ("DECOY2", "SMALLUSD", "1999-02-25"),
                           ("FBK", "BBB", "1999-03-01"),
                           ("ICHR", "LRCX", "1999-02-01"),
                           ("MAXSUP", "ZZZ", "1999-04-05"),
                           ("RANK", "ZZZCORP", "1999-02-15"),
                           ("TAGSUP", "ZZZ", "1999-04-01"),
                           ("ZOO", "LRCX", "1999-02-01")])

        # sorted by (filed, supplier, customer) -- NOT vacuous: the 1999q1 fixture rows
        # arrive out of this order (ZOO before ABC), so this only passes if
        # xbrl_build.main() actually calls links.sort(...).
        self.assertEqual(links, sorted(links, key=lambda x: (x["filed"], x["supplier"], x["customer"])))

    def test_principal_customer_is_the_larger_usd_revenue_one_not_alphabetical(self):
        """RANK discloses AAACORP ($1M) and ZZZCORP ($5M). Only ZZZCORP -- the larger
        revenue, alphabetically LATER -- must be emitted. A regression to
        sorted(customers)[0] would wrongly emit AAACORP and fail this test."""
        out = "xbrl_links_rank.json"
        entry.main("1999q1", "1999q1", out=out)
        links = [x for x in json.load(open(out)) if x["supplier"] == "RANK"]
        self.assertEqual(links, [{"supplier": "RANK", "customer": "ZZZCORP", "filed": "1999-02-15"}])

    def test_non_revenue_tag_does_not_win_despite_huge_value(self):
        """DECOY1 discloses a $9B AccountsReceivableNetCurrent row and a $100K genuine
        USD revenue row. The receivable must not be mistaken for revenue."""
        out = "xbrl_links_decoy1.json"
        entry.main("1999q1", "1999q1", out=out)
        links = [x for x in json.load(open(out)) if x["supplier"] == "DECOY1"]
        self.assertEqual(links, [{"supplier": "DECOY1", "customer": "SMALLREV", "filed": "1999-02-20"}])

    def test_non_usd_row_does_not_win_despite_huge_value(self):
        """DECOY2 discloses a EUR 9B revenue row and a USD 200K revenue row. Only the
        USD row is comparable and must win."""
        out = "xbrl_links_decoy2.json"
        entry.main("1999q1", "1999q1", out=out)
        links = [x for x in json.load(open(out)) if x["supplier"] == "DECOY2"]
        self.assertEqual(links, [{"supplier": "DECOY2", "customer": "SMALLUSD", "filed": "1999-02-25"}])

    def test_no_rankable_rows_falls_back_to_alphabetical_and_is_still_emitted(self):
        """FBK's two customers (YYY, BBB) carry no USD revenue tag at all. The group
        must still emit exactly one link, falling back to the alphabetically-first
        customer (BBB), not silently dropping the group."""
        out = "xbrl_links_fbk.json"
        entry.main("1999q1", "1999q1", out=out)
        links = [x for x in json.load(open(out)) if x["supplier"] == "FBK"]
        self.assertEqual(links, [{"supplier": "FBK", "customer": "BBB", "filed": "1999-03-01"}])

    def test_pre_asc606_tag_salesrevenuenet_is_rankable(self):
        """TAGSUP discloses ZZZ tagged SalesRevenueNet ($900) and AAA tagged Revenues
        ($100). ZZZ -- the larger revenue -- must be emitted. Before the ASC 606
        transition, SalesRevenueNet (and siblings) were the dominant revenue tags; a
        predicate of startswith("revenue") alone does not match "salesrevenuenet", so
        under the bug only AAA's row would rank and AAA would wrongly win."""
        out = "xbrl_links_tagsup.json"
        entry.main("1999q1", "1999q1", out=out)
        links = [x for x in json.load(open(out)) if x["supplier"] == "TAGSUP"]
        self.assertEqual(links, [{"supplier": "TAGSUP", "customer": "ZZZ", "filed": "1999-04-01"}])

    def test_principal_customer_is_max_not_sum_of_rankable_rows(self):
        """MAXSUP discloses AAA with three rankable rows of 100 each (sum 300, max 100)
        and ZZZ with one rankable row of 200 (sum 200, max 200). The correct principal
        is ZZZ: 200 > 100. Under a SUM aggregation AAA would wrongly win with 300; the
        alphabetical fallback would also (coincidentally) pick AAA, so this test catches
        a regression to either sum or to the fallback path."""
        out = "xbrl_links_maxsup.json"
        entry.main("1999q1", "1999q1", out=out)
        links = [x for x in json.load(open(out)) if x["supplier"] == "MAXSUP"]
        self.assertEqual(links, [{"supplier": "MAXSUP", "customer": "ZZZ", "filed": "1999-04-05"}])


if __name__ == "__main__":
    unittest.main()
