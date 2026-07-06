"""Offline test: the risk.py entry writes risk.json and fails soft."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import risk as entry  # noqa: E402


class TestEntry(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = os.path.join(os.path.dirname(__file__), "_risktmp")
        os.makedirs(self._tmp, exist_ok=True)
        os.chdir(self._tmp)

    def tearDown(self):
        import shutil
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_writes_risk_json_from_state(self):
        json.dump({"open": [{"supplier": "GILD", "customer": "CAH"}]}, open("paper_state.json", "w"))
        entry.build_risk = lambda state: {"generated_utc": "t", "model_used": "m",
            "per_idea": {"GILD|CAH": {"borrow": {"class": "na"}}}}
        entry.main()
        self.assertTrue(os.path.exists("risk.json"))
        self.assertIn("GILD|CAH", json.load(open("risk.json"))["per_idea"])

    def test_no_state_fails_soft(self):
        entry.main()
        self.assertFalse(os.path.exists("risk.json"))


if __name__ == "__main__":
    unittest.main()
