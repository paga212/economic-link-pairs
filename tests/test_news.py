"""Offline tests for the news fetchers (no network; urlopen monkeypatched)."""
import json
import os
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import elp.news as news  # noqa: E402

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Apple raises Mac prices - Reuters</title><link>http://x/1</link>
<pubDate>Fri, 26 Jun 2026 07:00:00 GMT</pubDate><source url="http://reuters.com">Reuters</source></item>
<item><title>Apple Creator Studio ships - Apple</title><link>http://x/2</link>
<pubDate>Tue, 30 Jun 2026 17:06:13 GMT</pubDate></item>
</channel></rss>"""

TIINGO = json.dumps([
    {"title": "Cardinal Health guides higher", "source": "bloomberg.com",
     "publishedDate": "2026-06-28T12:00:00Z", "url": "http://y/1"},
    {"title": "", "source": "x", "publishedDate": "2026-06-27T00:00:00Z", "url": "http://y/2"},
])


class _FakeResp:
    def __init__(self, data): self._d = data
    def read(self): return self._d
    def __enter__(self): return self
    def __exit__(self, *a): return False


class TestFetchers(unittest.TestCase):
    def test_google_rss_parses_items(self):
        news.urllib.request.urlopen = lambda req, timeout=20: _FakeResp(RSS.encode())
        items = news.google_rss("AAPL")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Apple raises Mac prices - Reuters")
        self.assertEqual(items[0]["source"], "Reuters")
        self.assertIn("2026", items[0]["date"])

    def test_tiingo_news_parses_and_drops_empty_titles(self):
        news.urllib.request.urlopen = lambda req, timeout=20: _FakeResp(TIINGO.encode())
        items = news.tiingo_news("CAH", start="2026-06-20")
        self.assertEqual(len(items), 1)                 # empty-title row dropped
        self.assertEqual(items[0]["title"], "Cardinal Health guides higher")
        self.assertEqual(items[0]["date"], "2026-06-28")

    def test_network_error_returns_empty_list(self):
        def boom(req, timeout=20): raise urllib.error.URLError("down")
        news.urllib.request.urlopen = boom
        self.assertEqual(news.google_rss("AAPL"), [])
        self.assertEqual(news.tiingo_news("CAH"), [])

    def test_tiingo_missing_token_returns_empty(self):
        orig = news._token
        news._token = lambda: (_ for _ in ()).throw(RuntimeError("no token"))
        try:
            self.assertEqual(news.tiingo_news("CAH"), [])
        finally:
            news._token = orig


if __name__ == "__main__":
    unittest.main()
