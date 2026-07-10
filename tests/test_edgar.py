"""Offline unit tests for EDGAR text parsing (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.edgar import concentration_snippets, extract_disclosures, norm  # noqa: E402
from elp.edgar import CATEGORY, _canonical, resolve_member, title_index  # noqa: E402


class TestEdgar(unittest.TestCase):
    def test_norm_strips_suffixes(self):
        self.assertEqual(norm("Apple Inc."), "apple")
        self.assertEqual(norm("Advanced Micro Devices, Inc."), "advanced micro devices")
        self.assertEqual(norm("The Boeing Company"), "boeing")

    def test_extract_name_then_pct(self):
        d = extract_disclosures(
            "In fiscal 2023, Apple Inc. accounted for approximately 85% of net sales.")
        self.assertTrue(any(x["customer"].startswith("Apple") and x["pct"] == 85.0 for x in d))

    def test_extract_pct_then_name(self):
        d = extract_disclosures(
            "Approximately 66% of total revenues were derived from Samsung Electronics.")
        self.assertTrue(any("Samsung" in x["customer"] and x["pct"] == 66.0 for x in d))

    def test_rejects_generic_leadins(self):
        # "One customer accounted for 12% of net sales" has no real name -> dropped
        d = extract_disclosures("One customer accounted for 12% of net sales.")
        self.assertEqual([x for x in d if x["customer"].lower().startswith("one")], [])

    def test_dedups(self):
        d = extract_disclosures(
            "Apple accounted for 85% of net sales. Apple accounted for 85% of net sales.")
        apple = [x for x in d if x["customer"].startswith("Apple") and x["pct"] == 85.0]
        self.assertEqual(len(apple), 1)


    def test_concentration_snippets(self):
        txt = ("Intro. " * 50 + "Apple Inc. accounted for 40% of net sales in fiscal 2023. "
               + "Filler. " * 50 + "Our largest customer represented 15% of revenue. " + "End. " * 50)
        snips = concentration_snippets(txt, window=60, maxn=4)
        self.assertTrue(snips and any("accounted for 40%" in s for s in snips))
        self.assertTrue(all(len(s) < 400 for s in snips))  # windows stay small

    def test_no_snippets_when_no_concentration_language(self):
        self.assertEqual(concentration_snippets("nothing relevant here " * 20), [])


class TestResolveMember(unittest.TestCase):
    """Customer members come from XBRL tags: 'AppleIncMember', 'CustomerAMember', 'OtherMember'."""

    def setUp(self):
        self.by_cik = {
            320193: {"ticker": "AAPL", "title": "Apple Inc."},
            1018724: {"ticker": "AMZN", "title": "AMAZON COM INC"},
            37996: {"ticker": "F", "title": "Ford Motor Co"},
            6951: {"ticker": "AMAT", "title": "APPLIED MATERIALS INC"},
            104169: {"ticker": "WMT", "title": "Walmart Inc."},
        }
        self.by_name = {}
        for row in self.by_cik.values():
            n = norm(row["title"])
            self.by_name.setdefault(n, row["ticker"])
            self.by_name.setdefault(n.replace(" ", ""), row["ticker"])
        self.titles = title_index(self.by_cik)

    def _r(self, m):
        return resolve_member(m, self.by_name, self.titles)

    def test_exact_match_after_stripping_member_suffix(self):
        self.assertEqual(self._r("WalmartInc"), "WMT")

    def test_exact_match_wins_before_any_widening(self):
        self.assertEqual(self._r("AppliedMaterials"), "AMAT")   # norm == 'applied materials'

    def test_unique_prefix_match_recovers_shortened_names(self):
        """'Amazon' is a strict prefix of the normalized title 'amazon com', and unique.
        'Ford' likewise prefixes 'ford motor'. Neither resolves by exact norm."""
        self.assertEqual(self._r("Amazon"), "AMZN")
        self.assertEqual(self._r("Ford"), "F")

    def test_rejects_anonymized_members(self):
        for m in ("CustomerAMember", "CustomerOneMember", "CustomerMember"):
            self.assertIsNone(self._r(m), m)

    def test_rejects_category_members(self):
        for m in ("OtherMember", "ExternalCustomersMember", "IntersegmentMember",
                  "ResidentialMember", "USGovernmentMember", "DistributionMember"):
            self.assertIsNone(self._r(m), m)

    def test_rejects_a_short_or_ambiguous_leading_token(self):
        self.assertIsNone(self._r("AbcMember"))          # leading token < 4 chars
        self.assertIsNone(self._r("ZzzzUnknownCoMember"))  # no title starts with it

    def test_ambiguous_prefix_is_rejected_not_guessed(self):
        by_cik = {1: {"ticker": "AAA", "title": "Delta Air Lines"},
                  2: {"ticker": "BBB", "title": "Delta Apparel"}}
        by_name = {norm(v["title"]): v["ticker"] for v in by_cik.values()}
        self.assertIsNone(resolve_member("Delta", by_name, title_index(by_cik)))


class TestCanonicalTicker(unittest.TestCase):
    def test_prefers_the_common_share_class(self):
        rows = {"0": {"cik_str": 37996, "ticker": "F-PD", "title": "Ford Motor Co"},
                "1": {"cik_str": 37996, "ticker": "F", "title": "Ford Motor Co"},
                "2": {"cik_str": 37996, "ticker": "F-PB", "title": "Ford Motor Co"}}
        self.assertEqual(_canonical(rows)[37996]["ticker"], "F")


if __name__ == "__main__":
    unittest.main()
