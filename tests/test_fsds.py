"""Offline unit tests for the SEC Financial Statement Data Sets reader (no network)."""
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.fsds import major_customers, quarters  # noqa: E402

SUB = "\t".join(["adsh", "cik", "filed"]) + "\n" + \
      "0000-24-1\t320193\t20240201\n" + \
      "0000-24-2\t789019\t20240315\n"

# One customer row, one row on a different axis, one row whose adsh is unknown.
# The Apple row carries a revenue tag in USD (the realistic case for ranking); the
# CustomerA row carries a percentage tag in "pure" (the realistic non-revenue case).
NUM = "\t".join(["adsh", "tag", "uom", "segments", "value"]) + "\n" + \
      "0000-24-1\tRevenueFromContractWithCustomerExcludingAssessedTax\tUSD\t" \
      "ConcentrationRiskByType=Cust;MajorCustomers=AppleIncMember;\t0.21\n" + \
      "0000-24-1\tConcentrationRiskPercentage1\tpure\tEquitySecuritiesByIndustry=SoftwareSector;\t0.13\n" + \
      "0000-24-2\tConcentrationRiskPercentage1\tpure\tMajorCustomers=CustomerAMember;\t\n" + \
      "0000-XX-9\tConcentrationRiskPercentage1\tpure\tMajorCustomers=GhostMember;\t0.99\n"


def _zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("sub.txt", SUB)
        z.writestr("num.txt", NUM)
    return path


class TestQuarters(unittest.TestCase):
    def test_enumerates_inclusive_range(self):
        self.assertEqual(quarters("2013q1", "2013q3"), ["2013q1", "2013q2", "2013q3"])

    def test_crosses_a_year_boundary(self):
        self.assertEqual(quarters("2013q4", "2014q2"), ["2013q4", "2014q1", "2014q2"])

    def test_single_quarter(self):
        self.assertEqual(quarters("2020q2", "2020q2"), ["2020q2"])


class TestMajorCustomers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.zip = _zip(os.path.join(self.tmp, "t.zip"))

    def test_extracts_only_major_customer_rows(self):
        rows = major_customers(self.zip)
        members = sorted(r["member"] for r in rows)
        self.assertEqual(members, ["AppleIncMember", "CustomerAMember"])

    def test_joins_cik_and_filed_date_from_sub(self):
        row = next(r for r in major_customers(self.zip) if r["member"] == "AppleIncMember")
        self.assertEqual(row["cik"], 320193)
        self.assertEqual(row["filed"], date(2024, 2, 1))
        self.assertAlmostEqual(row["value"], 0.21)

    def test_missing_value_becomes_none(self):
        row = next(r for r in major_customers(self.zip) if r["member"] == "CustomerAMember")
        self.assertIsNone(row["value"])

    def test_carries_tag_and_uom_for_revenue_row(self):
        row = next(r for r in major_customers(self.zip) if r["member"] == "AppleIncMember")
        self.assertEqual(row["tag"], "RevenueFromContractWithCustomerExcludingAssessedTax")
        self.assertEqual(row["uom"], "USD")

    def test_carries_tag_and_uom_for_non_revenue_row(self):
        row = next(r for r in major_customers(self.zip) if r["member"] == "CustomerAMember")
        self.assertEqual(row["tag"], "ConcentrationRiskPercentage1")
        self.assertEqual(row["uom"], "pure")

    def test_drops_rows_whose_filing_is_absent_from_sub(self):
        self.assertFalse([r for r in major_customers(self.zip) if r["member"] == "GhostMember"])

    def test_skips_unparseable_rows_and_continues(self):
        """Malformed filed dates or non-numeric values must be skipped without crashing."""
        tmp = tempfile.mkdtemp()
        zip_path = os.path.join(tmp, "unparseable.zip")

        # One good filing, one with malformed filed date (dashes instead of YYYYMMDD)
        sub = "\t".join(["adsh", "cik", "filed"]) + "\n" + \
              "0000-24-1\t320193\t20240201\n" + \
              "0000-24-2\t789019\t2024-03-15\n"

        # One good row, one with non-numeric value
        num = "\t".join(["adsh", "tag", "segments", "value"]) + "\n" + \
              "0000-24-1\tConcentrationRiskPercentage1\tMajorCustomers=AppleIncMember;\t0.21\n" + \
              "0000-24-2\tConcentrationRiskPercentage1\tMajorCustomers=CustomerAMember;\tN/A\n"

        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("sub.txt", sub)
            z.writestr("num.txt", num)

        # Should not raise; should return only the well-formed row
        rows = major_customers(zip_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["member"], "AppleIncMember")
        self.assertEqual(rows[0]["value"], 0.21)


if __name__ == "__main__":
    unittest.main()
