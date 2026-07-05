"""Deterministic news fetchers for the News/Catalyst agent (Phase 3). No LLM.

Recent headlines from two sources, each fail-soft to [] so a dead source never crashes a run:
- google_rss(query, days): Google News RSS search (keyless), parsed with stdlib xml.etree.
- tiingo_news(tickers, start, end): Tiingo /tiingo/news JSON (reuses the Tiingo token).
Both return [{"title","source","date","url"}]. Pure stdlib.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from elp.tiingo import _token

_UA = {"User-Agent": "Mozilla/5.0 (economic-link-pairs research)"}
_RSS = "https://news.google.com/rss/search"
_TIINGO_NEWS = "https://api.tiingo.com/tiingo/news"


def google_rss(query: str, days: int = 30) -> list[dict]:
    """Recent headlines for `query` from Google News RSS (keyless). [] on any error."""
    try:
        q = urllib.parse.quote(f"{query} when:{days}d")
        url = f"{_RSS}?q={q}&hl=en-US&gl=US&ceid=US:en"
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=20) as r:
            root = ET.fromstring(r.read())
        out = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            src = item.find("{*}source")
            out.append({"title": title,
                        "source": src.text.strip() if src is not None and src.text else "Google News",
                        "date": (item.findtext("pubDate") or "").strip(),
                        "url": (item.findtext("link") or "").strip()})
        return out
    except Exception:
        return []


def tiingo_news(tickers: str, start: str | None = None, end: str | None = None,
                limit: int = 20) -> list[dict]:
    """Recent Tiingo news for `tickers`, optionally date-windowed. [] on any error."""
    try:
        params = {"tickers": tickers, "limit": str(limit), "token": _token()}
        if start:
            params["startDate"] = start
        if end:
            params["endDate"] = end
        url = f"{_TIINGO_NEWS}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=20) as r:
            data = json.load(r)
        out = []
        for a in data if isinstance(data, list) else []:
            title = (a.get("title") or "").strip()
            if not title:
                continue
            out.append({"title": title, "source": a.get("source") or "Tiingo",
                        "date": (a.get("publishedDate") or "")[:10], "url": a.get("url") or ""})
        return out
    except Exception:
        return []
