"""Offline unit tests for EDGAR text parsing (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.edgar import extract_disclosures, norm  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
