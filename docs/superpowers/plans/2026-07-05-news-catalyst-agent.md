# News/Catalyst Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Phase-3 News/Catalyst agent that, per open idea, judges the customer catalyst and supplier confounding via a three-source ensemble (RSS + Tiingo + web search) reconciled by a master, and soft-derates ideas in the Fable-5 digest.

**Architecture:** Deterministic fetchers (`elp/news.py`) feed three independent Opus source-agents (`elp/catalyst.py`); a master Opus call reconciles them into one verdict per idea; `catalyst.py` writes `catalyst.json`; the digest prompt and the dashboard/email consume it. Every layer fails soft. Code fetches; the LLM only reasons.

**Tech Stack:** Python 3 stdlib only (`urllib`, `xml.etree`, `json`, `datetime`) + the existing `elp.llm` Anthropic client and `elp.tiingo` token loader. No new dependencies.

## Global Constraints

- **stdlib only** — no third-party deps (no pandas/numpy/requests).
- **Recommendations only** — never trades/moves money; soft-derate must NOT change engine open/close (hot-zone rule).
- **Numbers come from code, never an LLM** — agents emit only labels + prose (PLAN §2).
- **Fail soft everywhere** — a dead source → `[]` → `unknown` verdict; web search unavailable → two-source ensemble; whole step down → `digest.py` still runs. Never crash the `track → catalyst → digest → dashboard` pipeline.
- **Model:** all catalyst agents use Opus 4.8 (`claude-opus-4-8`) per PLAN §3/§5.
- **Offline tests** — no network/API socket in the unit suite (monkeypatch `urlopen` and the LLM call).
- **Reference spec:** `docs/superpowers/specs/2026-07-05-news-catalyst-agent-design.md`.

---

### Task 1: `elp/news.py` — deterministic news fetchers

**Files:**
- Create: `elp/news.py`
- Test: `tests/test_news.py`

**Interfaces:**
- Produces: `google_rss(query: str, days: int = 30) -> list[dict]` and
  `tiingo_news(tickers: str, start: str | None = None, end: str | None = None, limit: int = 20) -> list[dict]`.
  Each item is `{"title": str, "source": str, "date": str, "url": str}`. Both return `[]` on any error.

- [ ] **Step 1: Write the failing test** (`tests/test_news.py`)

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_news -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elp.news'`

- [ ] **Step 3: Write minimal implementation** (`elp/news.py`)

```python
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
    q = urllib.parse.quote(f"{query} when:{days}d")
    url = f"{_RSS}?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=20) as r:
            root = ET.fromstring(r.read())
    except (urllib.error.URLError, ET.ParseError, ValueError):
        return []
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


def tiingo_news(tickers: str, start: str | None = None, end: str | None = None,
                limit: int = 20) -> list[dict]:
    """Recent Tiingo news for `tickers`, optionally date-windowed. [] on any error."""
    params = {"tickers": tickers, "limit": str(limit), "token": _token()}
    if start:
        params["startDate"] = start
    if end:
        params["endDate"] = end
    url = f"{_TIINGO_NEWS}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=20) as r:
            data = json.load(r)
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        return []
    out = []
    for a in data if isinstance(data, list) else []:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        out.append({"title": title, "source": a.get("source") or "Tiingo",
                    "date": (a.get("publishedDate") or "")[:10], "url": a.get("url") or ""})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_news -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/news.py tests/test_news.py
git commit -m "feat(news): stdlib google_rss + tiingo_news fetchers (fail-soft)"
```

---

### Task 2: `elp/llm.py` — web-search server-tool support

**Files:**
- Modify: `elp/llm.py` (add `tools` param to `complete`; add `WEB_SEARCH_TOOL`)
- Test: `tests/test_llm.py` (create)

**Interfaces:**
- Consumes: existing `complete(prompt, model, max_tokens, system)`.
- Produces: `complete(..., tools: list | None = None)` — when `tools` is set, sends them in the body;
  text extraction is unchanged (final answer is still in `type == "text"` blocks). `WEB_SEARCH_TOOL: dict`.

- [ ] **Step 1: Write the failing test** (`tests/test_llm.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_llm -v`
Expected: FAIL — `AttributeError: module 'elp.llm' has no attribute 'WEB_SEARCH_TOOL'`

- [ ] **Step 3: Write minimal implementation** (edit `elp/llm.py`)

Add the constant after `_URL`:

```python
# Anthropic server tool: the API runs the search and returns results inline (no client loop).
# The exact `type` string is a dated identifier that may change; probe availability before relying.
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
```

Change the `complete` signature and body to accept `tools`:

```python
def complete(prompt: str, model: str = MODEL, max_tokens: int = 1024,
             system: str | None = None, tools: list | None = None) -> str:
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(_URL, data=json.dumps(body).encode(), headers={
        "x-api-key": _key(), "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise AnthropicError(f"Anthropic HTTP {e.code}", code=e.code) from None
    except urllib.error.URLError as e:
        raise AnthropicError(f"Anthropic network error: {e.reason}") from None
    return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_llm -v`
Expected: PASS

- [ ] **Step 5: Probe live availability (manual, informational — do not block)**

Run:
```bash
python3 -c "from elp.llm import complete, WEB_SEARCH_TOOL; print(complete('Search the web: what is the latest Apple product news? Answer in one line.', model='claude-opus-4-8', tools=[WEB_SEARCH_TOOL], max_tokens=400))"
```
Expected: a one-line answer citing recent news → web search is enabled. If it raises `AnthropicError HTTP 4xx`, web search is NOT enabled on this plan; that is fine — `web_agent` (Task 3) already degrades to `unknown`. Note the outcome in the commit message.

- [ ] **Step 6: Commit**

```bash
git add elp/llm.py tests/test_llm.py
git commit -m "feat(llm): optional web-search server tool in complete()"
```

---

### Task 3: `elp/catalyst.py` — source-agents + majority reducer

**Files:**
- Create: `elp/catalyst.py`
- Test: `tests/test_catalyst.py`

**Interfaces:**
- Consumes: `elp.news.google_rss`, `elp.news.tiingo_news`, `elp.llm.complete`, `elp.llm.parse_json`, `elp.llm.AnthropicError`, `elp.llm.WEB_SEARCH_TOOL`.
- Produces: `rss_agent(idea) -> dict`, `tiingo_agent(idea) -> dict`, `web_agent(idea) -> dict`
  (each `{"source", "customer_catalyst", "catalyst_note", "confounding_supplier_news", "confounding_note"}`),
  and `_majority(verdicts) -> {"customer_catalyst","confounding","confidence","note"}`.
  `idea` is a `paper_state.json` open row (`{"supplier","customer","entry", ...}`).

- [ ] **Step 1: Write the failing test** (`tests/test_catalyst.py`)

```python
"""Offline tests for the News/Catalyst agents (LLM + fetchers monkeypatched)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import elp.catalyst as catalyst  # noqa: E402

IDEA = {"supplier": "GILD", "customer": "CAH", "entry": "2026-06-25"}
HEAD = [{"title": "Cardinal Health raises guidance", "source": "BB", "date": "2026-06-24", "url": ""}]


class TestSourceAgents(unittest.TestCase):
    def tearDown(self):
        catalyst.google_rss = _orig_rss
        catalyst.tiingo_news = _orig_tiingo
        catalyst.complete = _orig_complete

    def test_source_verdict_prompt_includes_headlines_and_parses(self):
        seen = {}

        def fake_complete(prompt, **kw):
            seen["prompt"] = prompt
            return json.dumps({"customer_catalyst": "confirmed", "catalyst_note": "guidance up",
                               "confounding_supplier_news": "no", "confounding_note": "clean"})

        catalyst.complete = fake_complete
        v = catalyst._source_verdict("rss", "CAH", "GILD", HEAD, [])
        self.assertIn("Cardinal Health raises guidance", seen["prompt"])
        self.assertEqual(v["customer_catalyst"], "confirmed")
        self.assertEqual(v["source"], "rss")

    def test_no_headlines_short_circuits_to_unknown_without_calling_llm(self):
        def boom(*a, **k): raise AssertionError("LLM must not be called with no evidence")
        catalyst.complete = boom
        v = catalyst._source_verdict("tiingo", "CAH", "GILD", [], [])
        self.assertEqual(v["customer_catalyst"], "unknown")

    def test_rss_agent_wires_fetch_to_verdict(self):
        catalyst.google_rss = lambda q, days=30: HEAD if q == "CAH" else []
        catalyst.complete = lambda prompt, **kw: json.dumps(
            {"customer_catalyst": "weak", "catalyst_note": "", "confounding_supplier_news": "no",
             "confounding_note": ""})
        self.assertEqual(catalyst.rss_agent(IDEA)["customer_catalyst"], "weak")

    def test_web_agent_degrades_on_unavailable_tool(self):
        def raise_4xx(prompt, **kw): raise catalyst.AnthropicError("HTTP 400", code=400)
        catalyst.complete = raise_4xx
        v = catalyst.web_agent(IDEA)
        self.assertEqual(v["customer_catalyst"], "unknown")
        self.assertIn("web search", v["catalyst_note"].lower())


class TestMajority(unittest.TestCase):
    def test_majority_and_confounding_are_conservative(self):
        verdicts = [
            {"customer_catalyst": "confirmed", "confounding_supplier_news": "no"},
            {"customer_catalyst": "confirmed", "confounding_supplier_news": "yes"},
            {"customer_catalyst": "unknown", "confounding_supplier_news": "unknown"},
        ]
        m = catalyst._majority(verdicts)
        self.assertEqual(m["customer_catalyst"], "confirmed")   # mode of known verdicts
        self.assertEqual(m["confounding"], "yes")               # any 'yes' -> yes (conservative)

    def test_majority_all_unknown(self):
        m = catalyst._majority([{"customer_catalyst": "unknown"}])
        self.assertEqual(m["customer_catalyst"], "none")
        self.assertEqual(m["confidence"], "low")


_orig_rss = None
_orig_tiingo = None
_orig_complete = None


def setUpModule():
    global _orig_rss, _orig_tiingo, _orig_complete
    _orig_rss, _orig_tiingo, _orig_complete = catalyst.google_rss, catalyst.tiingo_news, catalyst.complete


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_catalyst -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elp.catalyst'`

- [ ] **Step 3: Write minimal implementation** (`elp/catalyst.py`)

```python
"""News/Catalyst agent (Phase 3): per open idea, three independent Opus source-agents judge the
customer catalyst + supplier confounding from RSS / Tiingo / web-search evidence; a master
reconciles them. Code fetches; the LLM only reasons — no agent emits a number. Fail-soft.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from elp.llm import AnthropicError, WEB_SEARCH_TOOL, complete, parse_json
from elp.news import google_rss, tiingo_news

OPUS = "claude-opus-4-8"

_SRC_SYS = (
    "You are a News/Catalyst analyst for a customer-supplier lead-lag trading system (a "
    "supplier's stock is slow to reflect news about its principal customer). Judge two things "
    "and return ONLY a JSON object: (1) did a GENUINE customer information event (earnings, "
    "guidance, a major deal/contract, product, regulatory) plausibly drive the customer's recent "
    "move; (2) is there SUPPLIER-specific news that already explains the supplier's move (a "
    "confound). Never invent events not supported by the evidence.")

_REC_SYS = (
    "You reconcile three independent News/Catalyst verdicts into one. Weigh agreement, recency, "
    "and relevance; ignore 'unknown' verdicts. Return ONLY a JSON object. Never invent facts.")

_SCHEMA = (
    'Return JSON: {"customer_catalyst":"confirmed|weak|none","catalyst_note":"<=15 words",'
    '"confounding_supplier_news":"yes|no","confounding_note":"<=15 words"}. '
    'If the evidence is empty or irrelevant, use "none"/"no" and say so.')


def _headlines_block(items: list, n: int = 8) -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  - {it['title']} ({it.get('date', '')})" for it in items[:n])


def _unknown(source: str, why: str) -> dict:
    return {"source": source, "customer_catalyst": "unknown", "catalyst_note": why,
            "confounding_supplier_news": "unknown", "confounding_note": why}


def _verdict_from(source: str, data: dict) -> dict:
    data = data or {}
    return {"source": source,
            "customer_catalyst": data.get("customer_catalyst", "unknown"),
            "catalyst_note": str(data.get("catalyst_note", "")).strip(),
            "confounding_supplier_news": data.get("confounding_supplier_news", "unknown"),
            "confounding_note": str(data.get("confounding_note", "")).strip()}


def _source_verdict(source: str, cust: str, sup: str, cust_items: list, sup_items: list) -> dict:
    """One Opus call judging catalyst + confounding from passed-in headlines. No evidence -> skip
    the call and return 'unknown' (saves cost)."""
    if not cust_items and not sup_items:
        return _unknown(source, "no headlines")
    prompt = (f"Idea: supplier {sup} <- principal customer {cust}.\n"
              f"Recent {cust} (customer) headlines:\n{_headlines_block(cust_items)}\n"
              f"Recent {sup} (supplier) headlines:\n{_headlines_block(sup_items)}\n" + _SCHEMA)
    return _verdict_from(source, parse_json(complete(prompt, model=OPUS, system=_SRC_SYS)))


def rss_agent(idea: dict) -> dict:
    cust, sup = idea["customer"], idea["supplier"]
    return _source_verdict("rss", cust, sup, google_rss(cust), google_rss(sup))


def tiingo_agent(idea: dict) -> dict:
    cust, sup = idea["customer"], idea["supplier"]
    start = None
    if idea.get("entry"):
        try:
            start = (date.fromisoformat(idea["entry"]) - timedelta(days=21)).isoformat()
        except ValueError:
            start = None
    return _source_verdict("tiingo", cust, sup, tiingo_news(cust, start=start),
                           tiingo_news(sup, start=start))


def web_agent(idea: dict) -> dict:
    cust, sup = idea["customer"], idea["supplier"]
    prompt = (f"Search recent (~30 days) news on customer {cust} and supplier {sup}. "
              f"Idea: supplier {sup} lags its principal customer {cust}.\n" + _SCHEMA)
    try:
        text = complete(prompt, model=OPUS, system=_SRC_SYS, tools=[WEB_SEARCH_TOOL], max_tokens=1500)
    except AnthropicError:
        return _unknown("web", "web search unavailable")
    return _verdict_from("web", parse_json(text))


def _majority(verdicts: list) -> dict:
    """Deterministic reducer (also the reconcile fallback): mode of known catalysts; confounding
    is 'yes' if ANY known source says yes (conservative)."""
    known = [v for v in verdicts if v.get("customer_catalyst") not in (None, "unknown")]
    if not known:
        return {"customer_catalyst": "none", "confounding": "no", "confidence": "low",
                "note": "no usable news from any source"}
    cat = Counter(v["customer_catalyst"] for v in known).most_common(1)[0][0]
    conf = "yes" if any(v.get("confounding_supplier_news") == "yes" for v in known) else "no"
    n, agree = len(known), sum(1 for v in known if v["customer_catalyst"] == cat)
    confidence = "high" if agree == n and n >= 2 else "med" if agree > n / 2 else "low"
    return {"customer_catalyst": cat, "confounding": conf, "confidence": confidence,
            "note": f"{agree}/{n} sources agree ({cat}); confounding={conf}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_catalyst -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/catalyst.py tests/test_catalyst.py
git commit -m "feat(catalyst): three source-agents + majority reducer"
```

---

### Task 4: `elp/catalyst.py` — reconcile, assess_idea, build_catalyst, catalyst_flag

**Files:**
- Modify: `elp/catalyst.py` (append)
- Test: `tests/test_catalyst.py` (append a class)

**Interfaces:**
- Consumes: `rss_agent`, `tiingo_agent`, `web_agent`, `_majority` (Task 3).
- Produces: `reconcile(cust: str, sup: str, verdicts: list) -> dict`,
  `assess_idea(idea: dict) -> dict` (final verdict + `"sources"` list),
  `build_catalyst(state: dict) -> {"generated_utc","model_used","per_idea": {"SUP|CUST": verdict}}`,
  `catalyst_flag(cv: dict | None) -> str`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_catalyst.py`, before the `_orig_*` block)

```python
class TestReconcileAndBuild(unittest.TestCase):
    def tearDown(self):
        catalyst.complete = _orig_complete

    def test_reconcile_parses_master_json(self):
        catalyst.complete = lambda prompt, **kw: json.dumps(
            {"customer_catalyst": "confirmed", "confounding": "no", "confidence": "high",
             "note": "Two sources confirm a guidance raise."})
        out = catalyst.reconcile("CAH", "GILD", [{"customer_catalyst": "confirmed"}])
        self.assertEqual(out["customer_catalyst"], "confirmed")
        self.assertEqual(out["confidence"], "high")

    def test_reconcile_falls_back_to_majority_on_bad_json(self):
        catalyst.complete = lambda prompt, **kw: "not json"
        verdicts = [{"customer_catalyst": "none", "confounding_supplier_news": "no"},
                    {"customer_catalyst": "none", "confounding_supplier_news": "no"}]
        out = catalyst.reconcile("CAH", "GILD", verdicts)
        self.assertEqual(out["customer_catalyst"], "none")   # from _majority

    def test_build_catalyst_keys_every_open_idea(self):
        catalyst.assess_idea = lambda idea: {"customer_catalyst": "weak", "confounding": "no",
                                             "confidence": "med", "note": "x", "sources": []}
        state = {"open": [{"supplier": "GILD", "customer": "CAH"},
                          {"supplier": "PG", "customer": "WMT"}]}
        c = catalyst.build_catalyst(state)
        self.assertEqual(set(c["per_idea"]), {"GILD|CAH", "PG|WMT"})
        self.assertEqual(c["model_used"], catalyst.OPUS)

    def test_catalyst_flag_text(self):
        self.assertIn("confounded", catalyst.catalyst_flag({"confounding": "yes"}))
        self.assertIn("confirmed", catalyst.catalyst_flag({"customer_catalyst": "confirmed",
                                                           "confounding": "no"}))
        self.assertIn("no clear", catalyst.catalyst_flag({"customer_catalyst": "none",
                                                          "confounding": "no"}))
        self.assertEqual(catalyst.catalyst_flag(None), "")
```

Note: `test_build_catalyst_keys_every_open_idea` monkeypatches `assess_idea`, so restore it — add `catalyst.assess_idea = _orig_assess` to this class's `tearDown` and capture `_orig_assess` in `setUpModule`. Update `setUpModule` and the module-level globals accordingly:

```python
# add to the module-level globals block:
_orig_assess = None
# and in setUpModule():
    global _orig_assess
    _orig_assess = catalyst.assess_idea
# and in TestReconcileAndBuild.tearDown():
        catalyst.assess_idea = _orig_assess
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_catalyst -v`
Expected: FAIL — `AttributeError: module 'elp.catalyst' has no attribute 'reconcile'`

- [ ] **Step 3: Write minimal implementation** (append to `elp/catalyst.py`)

```python
def reconcile(cust: str, sup: str, verdicts: list) -> dict:
    """Master Opus call folding the three source verdicts into one; deterministic _majority
    fallback if the model errors or returns unparseable JSON."""
    prompt = (f"Idea: supplier {sup} <- customer {cust}. Three independent verdicts:\n"
              f"{json.dumps(verdicts, indent=1)}\n"
              'Reconcile into ONE. Return JSON: {"customer_catalyst":"confirmed|weak|none",'
              '"confounding":"yes|no","confidence":"high|med|low","note":"one sentence for the reader"}.')
    try:
        data = parse_json(complete(prompt, model=OPUS, system=_REC_SYS, max_tokens=512))
    except AnthropicError:
        data = None
    if not isinstance(data, dict) or "customer_catalyst" not in data:
        return _majority(verdicts)
    return {"customer_catalyst": data.get("customer_catalyst", "none"),
            "confounding": data.get("confounding", "no"),
            "confidence": data.get("confidence", "low"),
            "note": str(data.get("note", "")).strip()}


def assess_idea(idea: dict) -> dict:
    verdicts = [rss_agent(idea), tiingo_agent(idea), web_agent(idea)]
    final = reconcile(idea["customer"], idea["supplier"], verdicts)
    final["sources"] = verdicts          # keep raw source verdicts for transparency/audit
    return final


def build_catalyst(state: dict) -> dict:
    per = {f'{o["supplier"]}|{o["customer"]}': assess_idea(o) for o in state.get("open", [])}
    return {"generated_utc": datetime.now(timezone.utc).isoformat(), "model_used": OPUS,
            "per_idea": per}


def catalyst_flag(cv: dict | None) -> str:
    """Short reader-facing flag, shared by dashboard + email."""
    if not cv:
        return ""
    if cv.get("confounding") == "yes":
        return "⚠ confounded (supplier news)"
    cat = cv.get("customer_catalyst")
    return {"confirmed": "catalyst: confirmed", "weak": "catalyst: weak",
            "none": "⚠ no clear catalyst"}.get(cat, "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_catalyst -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/catalyst.py tests/test_catalyst.py
git commit -m "feat(catalyst): reconcile master + assess_idea + build_catalyst + flag"
```

---

### Task 5: `catalyst.py` entry + pipeline wiring

**Files:**
- Create: `catalyst.py`
- Modify: `run_paper.sh` (insert `catalyst.py` before `digest.py`); `.gitignore` (ignore `catalyst.json`)
- Test: `tests/test_catalyst_entry.py`

**Interfaces:**
- Consumes: `elp.catalyst.build_catalyst`.
- Produces: `catalyst.json` (`{"generated_utc","model_used","per_idea"}`), gitignored. Fail-soft entry.

- [ ] **Step 1: Write the failing test** (`tests/test_catalyst_entry.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_catalyst_entry -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalyst'`

- [ ] **Step 3: Write minimal implementation** (`catalyst.py`)

```python
"""Daily News/Catalyst pass: per open idea, an Opus 3-source ensemble judges the customer
catalyst + supplier confounding, reconciled by a master. Writes catalyst.json (consumed by
digest.py / dashboard.py / email_report.py). Fails SOFT so the pipeline never breaks.

Run: python3 catalyst.py
"""
import json

from elp.catalyst import build_catalyst

STATE, OUT = "paper_state.json", "catalyst.json"


def main() -> None:
    try:
        state = json.load(open(STATE))
    except FileNotFoundError:
        print(f"[catalyst] no {STATE} yet — run track.py first; skipping")
        return
    if not state.get("open"):
        print("[catalyst] no open ideas; skipping")
        return
    try:
        c = build_catalyst(state)
    except Exception as e:                    # no key / API / network -> fail soft
        print(f"[catalyst] skipped ({type(e).__name__}: {e})")
        return
    json.dump(c, open(OUT, "w"), indent=1)
    print(f"wrote {OUT} | {len(c['per_idea'])} ideas assessed | model={c['model_used']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_catalyst_entry -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire the pipeline + gitignore**

Edit `run_paper.sh` — insert the catalyst line before the digest line so the digest sees fresh verdicts:

```bash
python3 track.py     >> paper_run.log 2>&1
python3 catalyst.py  >> paper_run.log 2>&1   # News/Catalyst ensemble -> catalyst.json (fails soft)
python3 digest.py    >> paper_run.log 2>&1   # Fable-5 digest; consumes catalyst.json
python3 dashboard.py >> paper_run.log 2>&1
```

Append to `.gitignore` (generated, like `digest.json`):

```
catalyst.json
```

- [ ] **Step 6: Commit**

```bash
git add catalyst.py tests/test_catalyst_entry.py run_paper.sh .gitignore
git commit -m "feat(catalyst): daily entry + pipeline wiring (track->catalyst->digest)"
```

---

### Task 6: Digest soft-derate — consume catalyst verdicts

**Files:**
- Modify: `elp/digest.py` (`_prompt` + `build_digest` take an optional `catalyst` map)
- Modify: `digest.py` (load `catalyst.json`, pass it in)
- Test: `tests/test_digest.py` (add a case)

**Interfaces:**
- Consumes: `catalyst.json` `per_idea` map keyed `"SUP|CUST"`.
- Produces: `_prompt(state, notes, catalyst=None)`, `build_digest(state, notes, catalyst=None)` — backward compatible (existing 2-arg calls unchanged).

- [ ] **Step 1: Write the failing test** (add to `tests/test_digest.py` `TestPrompt`)

```python
    def test_prompt_includes_catalyst_when_supplied(self):
        catalyst = {"SWKS|AAPL": {"customer_catalyst": "none", "confounding": "yes"}}
        p = _prompt(STATE, NOTES, catalyst)
        self.assertIn("catalyst=none", p)
        self.assertIn("confounded=yes", p)
        self.assertIn("rank", p.lower())         # instruction to down-rank exists
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_digest -v`
Expected: FAIL — `_prompt() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Write minimal implementation** (edit `elp/digest.py`)

Replace the `_prompt` signature/loop and the ranking instruction. New `_prompt`:

```python
def _prompt(state: dict, notes: dict, catalyst: dict | None = None) -> str:
    catalyst = catalyst or {}
    lines = ["Open paper trades (supplier <- principal customer | kind | days held | link | catalyst):"]
    for o in state.get("open", []):
        note = notes.get((o["supplier"], o["customer"]), "")
        kind = o.get("kind", "LONG" if o.get("side", 0) > 0 else "SHORT")
        cv = catalyst.get(f'{o["supplier"]}|{o["customer"]}')
        ctag = (f' | catalyst={cv.get("customer_catalyst", "?")}, '
                f'confounded={cv.get("confounding", "?")}') if cv else ""
        lines.append(f'- {o["supplier"]} <- {o["customer"]} | {kind} | {o["days"]}d | {note}{ctag}')
    if not state.get("open"):
        lines.append("- (none open right now)")
    st = state.get("stats", {}) or {}
    lines.append(f'\nClosed out-of-sample trades scored so far: n={st.get("n") or 0}.')
    lines.append(
        '\nReturn JSON exactly of this shape:\n'
        '{"summary": "2-3 short, declarative sentences reading the book as a whole",\n'
        ' "ranked": [{"supplier": "TICK", "rationale": "at most ~12 words on conviction, grounded '
        'in the economic link, no numbers; if the trade needs attention (thesis weakening, held a '
        'long time, near its stop) prefix the rationale with ⚠ and say why briefly"}]}\n'
        'Rank ALL open suppliers, most attractive first. Rank LOWER any idea whose catalyst is '
        '"none" or confounded="yes" (the signal is unconfirmed or already priced), and say so in '
        "its rationale. Use only the tickers listed above. Do NOT return a separate watch list."
    )
    return "\n".join(lines)
```

Change `build_digest` to accept and forward `catalyst`:

```python
def build_digest(state: dict, notes: dict, catalyst: dict | None = None) -> dict:
    text, model = complete_fallback(_prompt(state, notes, catalyst), primary=PRIMARY,
                                    fallback=FALLBACK, system=SYSTEM, max_tokens=4096)
```

(Leave the rest of `build_digest` unchanged.)

- [ ] **Step 4: Load catalyst.json in the entry** (edit `digest.py`)

```python
    notes = {(s, c): n for s, c, n in load_universe()}
    catalyst = {}
    try:
        catalyst = json.load(open("catalyst.json")).get("per_idea", {})
    except (FileNotFoundError, ValueError):
        pass
    try:
        d = build_digest(state, notes, catalyst)
    except Exception as e:                    # no key / API / network -> fail soft
        print(f"[digest] skipped ({type(e).__name__}: {e}) — dashboard keeps prior digest")
        return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_digest -v`
Expected: PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
git add elp/digest.py digest.py tests/test_digest.py
git commit -m "feat(digest): soft-derate ideas by catalyst verdict"
```

---

### Task 7: Show the catalyst flag on the dashboard + email

**Files:**
- Modify: `dashboard.py` (`build` loads `catalyst.json`; `idea_row(o, catalyst=None)` shows the flag)
- Modify: `email_report.py` (`render` loads `catalyst.json`; add the flag to each idea line)
- Test: `tests/test_dashboard.py`, `tests/test_email_report.py`

**Interfaces:**
- Consumes: `elp.catalyst.catalyst_flag`, `catalyst.json` `per_idea`.
- Produces: `idea_row(o: dict, catalyst: dict | None = None)` (backward compatible).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard.py` `TestIdeaRow`:

```python
    def test_row_shows_catalyst_flag_when_supplied(self):
        html = idea_row(IDEA, {"customer_catalyst": "none", "confounding": "yes"})
        self.assertIn("confounded", html)
```

Add to `tests/test_email_report.py` `TestRender.test_html_and_text_contain_the_ideas`, after building `html, text` — but that test calls `render(STATE, None)`; add a new test method:

```python
    def test_catalyst_flag_appears_when_catalyst_json_present(self):
        import email_report, json, os
        cwd = os.getcwd(); tmp = os.path.join(os.path.dirname(__file__), "_emailcat")
        os.makedirs(tmp, exist_ok=True); os.chdir(tmp)
        try:
            json.dump({"per_idea": {"GILD|CAH": {"customer_catalyst": "confirmed",
                       "confounding": "no"}}}, open("catalyst.json", "w"))
            html, text = email_report.render(STATE, None)
            self.assertIn("catalyst: confirmed", html)
        finally:
            os.chdir(cwd)
            import shutil; shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard tests.test_email_report -v`
Expected: FAIL — `idea_row() takes 1 positional argument but 2 were given`; email test fails (no flag).

- [ ] **Step 3: Implement dashboard** (edit `dashboard.py`)

Add the import at top: `from elp.catalyst import catalyst_flag`. Change `idea_row`:

```python
def idea_row(o, catalyst=None):
    """One idea as an HTML row: net direction + both legs + expression + catalyst flag."""
    direction = "LONG" if o["side"] > 0 else "SHORT"
    cap = "$10k hard" if o.get("risk_cap") == "hard" else "~$10k stop (gap risk)"
    rcls = "pos" if o["ret"] > 0 else "neg"
    flag = catalyst_flag(catalyst)
    fhtml = f"<br><span class=sub>{escape(flag)}</span>" if flag else ""
    return (
        f"<tr><td><b>{direction} {escape(o['supplier'])}</b><br>"
        f"<span class=sub>vs {escape(o['customer'])}</span>{fhtml}</td>"
        f"<td>{escape(o['expression'])}</td>"
        f"<td class=sub>primary: {escape(describe_leg(o['primary'], o['expression']))}<br>"
        f"neutralizer: {escape(describe_leg(o['neutralizer'], o['expression']))}</td>"
        f"<td>{escape(o['entry'])}</td><td>{o['days']}d</td>"
        f"<td class={rcls}>{o['ret']*100:+.1f}%</td>"
        f"<td class=sub>{cap}</td></tr>")
```

In `build()`, load the map and pass it to `idea_row`. Replace the `open_rows = ...` line:

```python
    try:
        cat = json.load(open("catalyst.json")).get("per_idea", {})
    except (FileNotFoundError, ValueError):
        cat = {}
    open_rows = "".join(idea_row(o, cat.get(f'{o["supplier"]}|{o["customer"]}')) for o in s["open"]) or \
        "<tr><td colspan=7 class=muted>no open ideas</td></tr>"
```

- [ ] **Step 4: Implement email** (edit `email_report.py`)

Add import: `from elp.catalyst import catalyst_flag`. In `render`, load the map once before the loop over `opens`:

```python
    try:
        cat = json.load(open("catalyst.json")).get("per_idea", {})
    except (FileNotFoundError, ValueError):
        cat = {}
```

Inside the `for o in opens:` loop, compute the flag and append it to both the HTML row (in the supplier cell) and the text line:

```python
        flag = catalyst_flag(cat.get(f'{o["supplier"]}|{o["customer"]}'))
```

In the HTML `rows +=` block, change the first cell to include the flag:

```python
        rows += (f'<tr><td style="{td}"><b>{direction} {escape(o["supplier"])}</b>'
                 f'<div style="color:#888;font-size:12px">vs {escape(o["customer"])} · {o["days"]}d'
                 + (f' · {escape(flag)}' if flag else '') + '</div></td>'
                 f'<td style="{td};font-size:13px">{escape(o["expression"])}</td>'
                 f'<td style="{td};font-size:12px;color:#444">{escape(p)}<br>{escape(n)}</td>'
                 f'<td style="{td};color:{col};font-weight:600;text-align:right">{o["ret"]*100:+.1f}%</td></tr>')
```

And append the flag to the text line:

```python
        tlines.append(f'{direction} {o["supplier"]} vs {o["customer"]} [{o["expression"]}] '
                      f'{o["ret"]*100:+.1f}%' + (f' [{flag}]' if flag else '') + f' | {p}; {n}')
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: OK (all tests, including the new dashboard/email catalyst cases).

- [ ] **Step 6: Commit**

```bash
git add dashboard.py email_report.py tests/test_dashboard.py tests/test_email_report.py
git commit -m "feat(ui): show catalyst flag on dashboard + email"
```

---

## Verification (whole feature, end-to-end)

1. **Full offline suite green:** `python3 -m unittest discover -s tests` → OK.
2. **Live smoke (spends a few cents; authorized like the digest run):**
   - `python3 track.py` (refresh `paper_state.json`) then `python3 catalyst.py` → prints `wrote catalyst.json | N ideas assessed`; open `catalyst.json` and confirm each open idea has a final verdict + three `sources`. Note whether the `web` source verdicts are real or `unknown` (tells you if web search is enabled).
   - `python3 digest.py` → runs; `python3 dashboard.py` → the Daily read down-ranks any `none`/confounded idea, and each Open-trades row shows its catalyst flag.
   - `EMAIL_DRYRUN=1 python3 email_report.py` → `email_report.eml` shows the catalyst flag on each idea line.
3. **Fail-soft check:** temporarily rename `.tiingo_token`/`.anthropic_key` and run `python3 catalyst.py` → prints a `[catalyst] skipped` line and exits 0; `digest.py`/`dashboard.py` still run without catalyst context. Restore the files.

## Self-Review

**Spec coverage:** §2 architecture → Tasks 3-4 (3 agents + reconcile). §3.1 fetchers → Task 1. §3.2 web-search → Task 2. §3.3 agent fleet/reconciler/build → Tasks 3-4. §3.4 entry → Task 5. §4 soft-derate wiring → Tasks 5-7. §5 degradation → fail-soft in Tasks 1,3,4,5 + verification step 3. §6 testing → tests in every task. §7 cost → documented (no code). §8 out-of-scope → honored (no engine change, no backfill, no paid feed).

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** verdict dict keys are consistent across tasks — source verdicts use `customer_catalyst`/`confounding_supplier_news`; the reconciled/final verdict uses `customer_catalyst`/`confounding` (Task 4 `reconcile` + `catalyst_flag` + Task 6 `_prompt` all read `customer_catalyst` and `confounding`). `per_idea` keys are `"SUP|CUST"` everywhere they are written (Task 4 `build_catalyst`) and read (Tasks 6-7). `idea_row(o, catalyst=None)` and `_prompt(state, notes, catalyst=None)` are optional-arg-compatible with existing callers/tests.

## Out of scope (deliberately)
- No change to trade open/close (soft-derate only); hard catalyst-gating stays reserved for the deferred options overlay (PLAN §11.1).
- No historical catalyst backfill; no company-name resolution for queries (tickers only — an easy later improvement via `elp.edgar.load_ticker_map`); no paid news feed.
