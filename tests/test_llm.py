"""Offline test: complete() forwards tools in the request body (urlopen monkeypatched)."""
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import elp.llm as llm  # noqa: E402


class TestTools(unittest.TestCase):
    def test_tools_forwarded_and_text_extracted(self):
        captured = {}

        class _Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(req, timeout=60):
            captured["body"] = json.loads(req.data.decode())
            return _Resp(json.dumps({"content": [
                {"type": "web_search_tool_result", "content": []},
                {"type": "text", "text": "answer"}]}).encode())

        llm.urllib.request.urlopen = fake_urlopen
        llm._key = lambda: "sk-test"
        out = llm.complete("hi", model="claude-opus-4-8", tools=[llm.WEB_SEARCH_TOOL])
        self.assertEqual(out, "answer")
        self.assertEqual(captured["body"]["tools"], [llm.WEB_SEARCH_TOOL])


if __name__ == "__main__":
    unittest.main()
