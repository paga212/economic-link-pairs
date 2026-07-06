"""Offline test: the catalyst.py entry writes catalyst.json and fails soft."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalyst as entry  # noqa: E402


class TestEntry(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = os.path.join(os.path.dirname(__file__), "_cattmp")
        os.makedirs(self._tmp, exist_ok=True)
        os.chdir(self._tmp)

    def tearDown(self):
        import shutil
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_writes_catalyst_json_from_state(self):
        json.dump({"open": [{"supplier": "GILD", "customer": "CAH"}]}, open("paper_state.json", "w"))
        entry.build_catalyst = lambda state: {"generated_utc": "t", "model_used": "m",
                                              "per_idea": {"GILD|CAH": {"customer_catalyst": "weak"}}}
        entry.main()
        self.assertTrue(os.path.exists("catalyst.json"))
        self.assertIn("GILD|CAH", json.load(open("catalyst.json"))["per_idea"])

    def test_no_state_fails_soft(self):
        entry.main()                          # no paper_state.json -> must not raise
        self.assertFalse(os.path.exists("catalyst.json"))


if __name__ == "__main__":
    unittest.main()
