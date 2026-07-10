"""Offline test: the xbrl_build.py entry dedupes/sorts/filters and writes JSON. No network."""
import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xbrl_build as entry  # noqa: E402

BY_CIK = {1: {"ticker": "ICHR", "title": "Ichor Holdings"},
          2: {"ticker": "LRCX", "title": "Lam Research"},
          3: {"ticker": "DAN", "title": "Dana Inc"},
          4: {"ticker": "SELF", "title": "Self Supplier Corp"}}
BY_NAME = {}
TITLES = {}

# rows keyed by quarter; each row: {cik, member, filed, value}
ROWS_BY_Q = {
    "2024q1": [
        # resolves to LRCX -> a real link, appears twice (dup filed date) -> dedup to 1
        {"cik": 1, "member": "LamResearchMember", "filed": date(2024, 2, 1), "value": 1e6},
        {"cik": 1, "member": "LamResearchMember", "filed": date(2024, 2, 1), "value": 1e6},
        # unresolvable member -> dropped
        {"cik": 1, "member": "OtherMember", "filed": date(2024, 2, 1), "value": 5e5},
        # self-link -> dropped (customer resolves to same ticker as supplier)
        {"cik": 4, "member": "SelfSupplierCorpMember", "filed": date(2024, 2, 1), "value": 1e5},
    ],
    "2024q2": [
        # a second, later disclosure of the same DAN link
        {"cik": 3, "member": "LamResearchMember", "filed": date(2024, 5, 1), "value": 2e6},
    ],
}


def fake_fetch_quarter(q, dest):
    open(dest, "w").write("fake")
    return dest


def fake_major_customers(zip_path):
    q = os.path.basename(zip_path).replace("fsds_", "").replace(".zip", "")
    return ROWS_BY_Q.get(q, [])


def fake_resolve_member(member, by_name, titles):
    if member == "LamResearchMember":
        return "LRCX"
    if member == "SelfSupplierCorpMember":
        return "SELF"
    return None


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
        entry.main("2024q1", "2024q2", out=out)
        self.assertTrue(os.path.exists(out))
        links = json.load(open(out))

        # self-link (SELF<-SELF) and unresolvable (OtherMember) must be dropped
        for x in links:
            self.assertNotEqual(x["supplier"], x["customer"])
        self.assertEqual({frozenset(x.keys()) for x in links}, {frozenset({"supplier", "customer", "filed"})})

        # dedup on (supplier, customer, filed): the duplicate 2024q1 row collapses to one
        keys = [(x["supplier"], x["customer"], x["filed"]) for x in links]
        self.assertEqual(len(keys), len(set(keys)))

        # two distinct links survive: ICHR<-LRCX (2024-02-01) and DAN<-LRCX (2024-05-01)
        self.assertEqual(sorted((x["supplier"], x["customer"], x["filed"]) for x in links),
                          [("DAN", "LRCX", "2024-05-01"), ("ICHR", "LRCX", "2024-02-01")])

        # sorted by (filed, supplier, customer)
        self.assertEqual(links, sorted(links, key=lambda x: (x["filed"], x["supplier"], x["customer"])))


if __name__ == "__main__":
    unittest.main()
