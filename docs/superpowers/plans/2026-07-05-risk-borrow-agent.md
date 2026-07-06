# Risk/Borrow Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Phase-3 Risk/Borrow agent that, per open idea, computes borrow / earnings-window / liquidity risk deterministically (Tiingo + `elp/liquidity.py`), has a thin Opus call narrate it, and soft-derates risky ideas in the Fable-5 digest.

**Architecture:** Deterministic core `elp/risk.py` (borrow proxy from market cap + ADV, next-earnings cadence estimate, liquidity re-check) plus a fail-soft one-line Opus narration; `risk.py` writes `risk.json`; the digest, dashboard, and email consume it. Numbers are code-computed; the LLM only narrates. Never touches engine open/close.

**Tech Stack:** Python 3 stdlib only + existing `elp.tiingo`, `elp.liquidity`, `elp.llm`. No new deps.

## Global Constraints

- **stdlib only** — no third-party deps.
- **Recommendations only** — soft-derate must NOT change engine open/close (hot-zone rule).
- **Numbers from code, never an LLM** — `narrate` adds no numbers; all figures are deterministic.
- **Fail soft everywhere** — every fetch → `None`/`[]`; missing data → conservative labels; `narrate` failure → `""`; `risk.py` wraps `build_risk` in `except Exception`; absent `risk.json` → no risk context. Never crash the `track → catalyst → risk → digest → dashboard` pipeline.
- **Model:** the narration call uses Opus 4.8 (`claude-opus-4-8`).
- **Hard-borrow copy:** a hard-to-borrow short is flagged `⚠ hard to borrow — short via options`, never "untradeable".
- **Offline tests** — no network/API socket in the suite (monkeypatch fetches and the LLM call).
- **Reference spec:** `docs/superpowers/specs/2026-07-05-risk-borrow-agent-design.md`.

---

### Task 1: `elp/tiingo.py` — fundamentals helpers

**Files:**
- Modify: `elp/tiingo.py` (append two functions + one URL constant)
- Test: `tests/test_tiingo.py` (append a class)

**Interfaces:**
- Consumes: existing `_fetch(url, symbol) -> list` (raises on HTTP error).
- Produces: `fetch_marketcap(ticker: str) -> float | None`, `fetch_statement_dates(ticker: str) -> list[str]`. Both fail soft.

- [ ] **Step 1: Write the failing test** (append to `tests/test_tiingo.py`)

```python
import elp.tiingo as _tiingo  # noqa: E402


class TestFundamentals(unittest.TestCase):
    def tearDown(self):
        _tiingo._fetch = _ORIG_FETCH

    def test_marketcap_takes_latest_nonzero(self):
        _tiingo._fetch = lambda url, sym: [
            {"date": "2026-06-01", "marketCap": 100.0}, {"date": "2026-07-01", "marketCap": 250.0}]
        self.assertEqual(_tiingo.fetch_marketcap("AMGN"), 250.0)

    def test_statement_dates_sorted_unique(self):
        _tiingo._fetch = lambda url, sym: [
            {"date": "2026-03-31T00:00:00.000Z"}, {"date": "2025-12-31T00:00:00.000Z"},
            {"date": "2025-12-31T00:00:00.000Z"}]
        self.assertEqual(_tiingo.fetch_statement_dates("AMGN"), ["2025-12-31", "2026-03-31"])

    def test_fetch_error_fails_soft(self):
        def boom(url, sym): raise RuntimeError("Tiingo HTTP 403")
        _tiingo._fetch = boom
        self.assertIsNone(_tiingo.fetch_marketcap("X"))
        self.assertEqual(_tiingo.fetch_statement_dates("X"), [])


_ORIG_FETCH = None


def setUpModule():
    global _ORIG_FETCH
    _ORIG_FETCH = _tiingo._fetch
```

(If `tests/test_tiingo.py` has no `unittest`/imports yet, mirror the header of `tests/test_news.py`: `import os, sys, unittest` and the `sys.path.insert(...)` line. Keep any existing content.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tiingo -v`
Expected: FAIL — `AttributeError: module 'elp.tiingo' has no attribute 'fetch_marketcap'`

- [ ] **Step 3: Write minimal implementation** (append to `elp/tiingo.py`)

```python
_FUND = "https://api.tiingo.com/tiingo/fundamentals/{sym}/{kind}"


def fetch_marketcap(ticker: str) -> float | None:
    """Latest non-zero marketCap from Tiingo fundamentals daily. None on any error/empty."""
    try:
        rows = _fetch(_FUND.format(sym=ticker.lower(), kind="daily"), ticker)
        for r in reversed(rows):
            mc = r.get("marketCap")
            if mc:
                return float(mc)
    except Exception:
        return None
    return None


def fetch_statement_dates(ticker: str) -> list[str]:
    """Sorted unique fiscal period-end dates (YYYY-MM-DD) from Tiingo statements. [] on error."""
    try:
        rows = _fetch(_FUND.format(sym=ticker.lower(), kind="statements"), ticker)
        return sorted({r["date"][:10] for r in rows if r.get("date")})
    except Exception:
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tiingo -v`
Expected: PASS (3 new tests)

- [ ] **Step 5: Commit**

```bash
git add elp/tiingo.py tests/test_tiingo.py
git commit -m "feat(tiingo): fail-soft fetch_marketcap + fetch_statement_dates"
```

---

### Task 2: `elp/risk.py` — pure risk functions

**Files:**
- Create: `elp/risk.py` (constants + `borrow_class`, `next_earnings_est`, `reported_since_entry`, `_latest`)
- Test: `tests/test_risk.py`

**Interfaces:**
- Produces: `borrow_class(ticker, direction, instrument, marketcap, adv) -> "easy"|"hard"|"na"`;
  `next_earnings_est(period_end_dates: list[str], today: date) -> tuple[date|None, int|None]`;
  `reported_since_entry(period_end_dates: list[str], entry: date, today: date) -> bool`.
  Constants `BORROW_MKTCAP_MIN`, `BORROW_ADV_MIN`, `CADENCE_DAYS`, `ANNOUNCE_LAG`, `HEDGE_ETF`.

- [ ] **Step 1: Write the failing test** (`tests/test_risk.py`)

```python
"""Offline tests for the Risk/Borrow agent (no network; fetches + LLM monkeypatched)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import elp.risk as risk  # noqa: E402
from elp.risk import borrow_class, next_earnings_est, reported_since_entry  # noqa: E402


class TestPure(unittest.TestCase):
    def test_borrow_class(self):
        # non-short stock leg -> na
        self.assertEqual(borrow_class("GILD", 1, "stock", 5e10, 1e8), "na")
        # short spread -> na (only short STOCK needs borrow)
        self.assertEqual(borrow_class("PG", -1, "spread", 5e10, 1e8), "na")
        # short ETF hedge -> easy
        self.assertEqual(borrow_class("SPY", -1, "stock", None, 0.0), "easy")
        # short large-cap liquid stock -> easy
        self.assertEqual(borrow_class("VC", -1, "stock", 5e9, 5e7), "easy")
        # short small-cap stock -> hard
        self.assertEqual(borrow_class("MZTI", -1, "stock", 5e8, 1e6), "hard")
        # missing marketcap -> hard (conservative)
        self.assertEqual(borrow_class("MZTI", -1, "stock", None, 5e7), "hard")

    def test_next_earnings_est_future_and_past_last_announce(self):
        # last period end 2026-03-31; +40d announce = 2026-05-10 < today -> next = +131d
        d, days = next_earnings_est(["2026-03-31"], date(2026, 7, 5))
        self.assertEqual(d, date(2026, 8, 9))
        self.assertEqual(days, 35)
        # last period end 2026-06-28; +40d = 2026-08-07 >= today -> that IS next
        d2, _ = next_earnings_est(["2026-06-28"], date(2026, 7, 5))
        self.assertEqual(d2, date(2026, 8, 7))
        # no dates -> (None, None)
        self.assertEqual(next_earnings_est([], date(2026, 7, 5)), (None, None))

    def test_reported_since_entry(self):
        # last announce 2026-05-10; entry 2026-04-01 < 2026-05-10 <= today -> True
        self.assertTrue(reported_since_entry(["2026-03-31"], date(2026, 4, 1), date(2026, 7, 5)))
        # entry AFTER the last announce -> False
        self.assertFalse(reported_since_entry(["2026-03-31"], date(2026, 6, 1), date(2026, 7, 5)))
        self.assertFalse(reported_since_entry([], date(2026, 4, 1), date(2026, 7, 5)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_risk -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elp.risk'`

- [ ] **Step 3: Write minimal implementation** (`elp/risk.py`)

```python
"""Risk/Borrow agent (Phase 3): per open idea, deterministic borrow / earnings-window / liquidity
facts, narrated by a thin Opus call. Soft-derates risky ideas in the digest. Numbers are computed
in code; the LLM only narrates. Fail-soft. Recommendations only.
"""
from __future__ import annotations

from datetime import date, timedelta

BORROW_MKTCAP_MIN = 2e9        # small-cap short borrow is often tight; crude proxy (no free feed)
BORROW_ADV_MIN = 20e6
CADENCE_DAYS = 91              # ~one fiscal quarter
ANNOUNCE_LAG = 40             # ~days from fiscal period end to the earnings announcement
HEDGE_ETF = "SPY"


def borrow_class(ticker, direction, instrument, marketcap, adv) -> str:
    """'na' unless the leg is a short stock; 'easy' for the broad ETF or a large, liquid name;
    else 'hard' (Grade-C market-cap + ADV proxy — there is no free borrow-fee feed)."""
    if not (instrument == "stock" and direction < 0):
        return "na"
    if ticker == HEDGE_ETF:
        return "easy"
    if marketcap is not None and marketcap >= BORROW_MKTCAP_MIN and adv >= BORROW_ADV_MIN:
        return "easy"
    return "hard"


def _latest(period_end_dates: list[str]):
    ds = sorted({date.fromisoformat(d[:10]) for d in period_end_dates if d}, reverse=True)
    return ds[0] if ds else None


def next_earnings_est(period_end_dates, today):
    """Estimated NEXT earnings-announcement date + days-to, from the latest fiscal period end.
    (None, None) if no dates. A cadence estimate, not the announced date."""
    last = _latest(period_end_dates)
    if last is None:
        return None, None
    last_announce = last + timedelta(days=ANNOUNCE_LAG)
    nxt = last_announce if last_announce >= today else last + timedelta(days=CADENCE_DAYS + ANNOUNCE_LAG)
    return nxt, (nxt - today).days


def reported_since_entry(period_end_dates, entry, today) -> bool:
    """Did the estimated most-recent announcement fall between entry and today (edge likely spent)?"""
    last = _latest(period_end_dates)
    if last is None:
        return False
    last_announce = last + timedelta(days=ANNOUNCE_LAG)
    return entry < last_announce <= today
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_risk -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/risk.py tests/test_risk.py
git commit -m "feat(risk): pure borrow/earnings-window primitives"
```

---

### Task 3: `elp/risk.py` — assess_idea_risk, narrate, build_risk, risk_flag

**Files:**
- Modify: `elp/risk.py` (append)
- Test: `tests/test_risk.py` (append a class)

**Interfaces:**
- Consumes: `borrow_class`, `next_earnings_est`, `reported_since_entry` (Task 2); `elp.liquidity.dollar_adv`/`is_tradeable`; `elp.tiingo.fetch_daily_bars`/`fetch_marketcap`/`fetch_statement_dates`; `elp.llm.complete`/`AnthropicError`.
- Produces: `assess_idea_risk(idea, bars_fn=?, mktcap_fn=?, dates_fn=?, today=None) -> dict`;
  `narrate(idea, facts) -> str`; `build_risk(state) -> {"generated_utc","model_used","per_idea": {"SUP|CUST": {**facts, "note"}}}`; `risk_flag(rv) -> str`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_risk.py`, before the `if __name__` block)

```python
class TestOrchestration(unittest.TestCase):
    def tearDown(self):
        risk.complete = _ORIG_COMPLETE

    def _bars(self, t):  # liquid stub: (date, price, volume) x 63, $50M ADV
        return [(date(2026, 1, 1), 50.0, 1_000_000.0)] * 63

    def test_long_pair_flags_hard_borrow_on_small_neutralizer(self):
        idea = {"supplier": "GILD", "customer": "CAH", "side": 1, "entry": "2026-06-25",
                "primary": {"role": "primary", "ticker": "GILD", "direction": 1, "instrument": "stock"},
                "neutralizer": {"role": "neutralizer", "ticker": "MZTI", "direction": -1, "instrument": "stock"}}
        facts = risk.assess_idea_risk(idea, bars_fn=self._bars,
                                      mktcap_fn=lambda t: 5e8,          # small cap -> hard
                                      dates_fn=lambda t: ["2026-03-31"], today=date(2026, 7, 5))
        self.assertEqual(facts["borrow"]["ticker"], "MZTI")
        self.assertEqual(facts["borrow"]["class"], "hard")
        self.assertEqual(facts["liquidity"], "ok")

    def test_short_spread_idea_has_no_borrow(self):
        idea = {"supplier": "PG", "customer": "WMT", "side": -1, "entry": "2026-07-01",
                "primary": {"role": "primary", "ticker": "PG", "direction": -1, "instrument": "spread"},
                "neutralizer": {"role": "neutralizer", "ticker": "SPY", "direction": 1, "instrument": "stock"}}
        facts = risk.assess_idea_risk(idea, bars_fn=self._bars, mktcap_fn=lambda t: 5e9,
                                      dates_fn=lambda t: [], today=date(2026, 7, 5))
        self.assertEqual(facts["borrow"]["class"], "na")

    def test_assess_degrades_when_fetch_raises(self):
        def boom(t): raise RuntimeError("net down")
        idea = {"supplier": "GILD", "customer": "CAH", "side": 1, "entry": "2026-06-25",
                "primary": {"ticker": "GILD", "direction": 1, "instrument": "stock"},
                "neutralizer": {"ticker": "MZTI", "direction": -1, "instrument": "stock"}}
        facts = risk.assess_idea_risk(idea, bars_fn=boom, mktcap_fn=boom, dates_fn=boom,
                                      today=date(2026, 7, 5))            # must NOT raise
        self.assertIn(facts["liquidity"], ("ok", "thin"))

    def test_narrate_fails_soft(self):
        def boom(*a, **k): raise risk.AnthropicError("HTTP 500", code=500)
        risk.complete = boom
        self.assertEqual(risk.narrate({"supplier": "X", "customer": "Y"}, {}), "")

    def test_build_risk_keys_every_idea(self):
        risk.assess_idea_risk = lambda o, **k: {"borrow": {"ticker": None, "class": "na"},
            "earnings": {"days_to": 30, "reported_since_entry": False}, "liquidity": "ok"}
        risk.narrate = lambda idea, facts: ""
        state = {"open": [{"supplier": "GILD", "customer": "CAH"}, {"supplier": "PG", "customer": "WMT"}]}
        out = risk.build_risk(state)
        self.assertEqual(set(out["per_idea"]), {"GILD|CAH", "PG|WMT"})
        self.assertEqual(out["model_used"], risk.OPUS)

    def test_risk_flag_precedence(self):
        self.assertIn("hard to borrow", risk.risk_flag({"borrow": {"class": "hard"}}))
        self.assertIn("post-earnings", risk.risk_flag({"borrow": {"class": "na"},
            "earnings": {"reported_since_entry": True}}))
        self.assertIn("thin", risk.risk_flag({"borrow": {"class": "na"},
            "earnings": {"reported_since_entry": False}, "liquidity": "thin"}))
        self.assertEqual(risk.risk_flag(None), "")
```

Add the module-level original-capture at the bottom (near the existing `if __name__`):

```python
_ORIG_COMPLETE = None
_ORIG_ASSESS = None
_ORIG_NARRATE = None


def setUpModule():
    global _ORIG_COMPLETE, _ORIG_ASSESS, _ORIG_NARRATE
    _ORIG_COMPLETE, _ORIG_ASSESS, _ORIG_NARRATE = risk.complete, risk.assess_idea_risk, risk.narrate
```

And in `TestOrchestration.tearDown` also restore the two that `test_build_risk_keys_every_idea` patches:

```python
        risk.assess_idea_risk = _ORIG_ASSESS
        risk.narrate = _ORIG_NARRATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_risk -v`
Expected: FAIL — `AttributeError: module 'elp.risk' has no attribute 'assess_idea_risk'`

- [ ] **Step 3: Write minimal implementation** (append to `elp/risk.py`)

```python
import json
from datetime import datetime, timezone

from elp.liquidity import dollar_adv, is_tradeable
from elp.llm import AnthropicError, complete, parse_json  # noqa: F401  (parse_json kept for symmetry)
from elp.tiingo import fetch_daily_bars, fetch_marketcap, fetch_statement_dates

OPUS = "claude-opus-4-8"

_NARRATE_SYS = (
    "You are a risk analyst for a customer-supplier lead-lag paper-trade. Given pre-computed risk "
    "facts, write ONE short plain sentence for the reader. Never add or change a number. "
    "Recommendations only.")


def _safe_bars(bars_fn, t):
    try:
        return bars_fn(t) or []
    except Exception:
        return []


def _short_stock_leg(idea: dict):
    for role in ("primary", "neutralizer"):
        leg = idea.get(role) or {}
        if leg.get("instrument") == "stock" and leg.get("direction", 0) < 0:
            return leg
    return None


def assess_idea_risk(idea, bars_fn=fetch_daily_bars, mktcap_fn=fetch_marketcap,
                     dates_fn=fetch_statement_dates, today=None) -> dict:
    """Deterministic borrow / earnings-window / liquidity facts. Every fetch is fail-soft, so
    missing data yields conservative labels rather than a raise."""
    today = today or datetime.now(timezone.utc).date()
    sup = idea["supplier"]
    liquidity = "ok" if is_tradeable(_safe_bars(bars_fn, sup)) else "thin"

    leg = _short_stock_leg(idea)
    if leg:
        t = leg["ticker"]
        try:
            mc = mktcap_fn(t)
        except Exception:
            mc = None
        bclass = borrow_class(t, leg["direction"], leg["instrument"], mc,
                              dollar_adv(_safe_bars(bars_fn, t)))
        borrow = {"ticker": t, "class": bclass}
    else:
        borrow = {"ticker": None, "class": "na"}

    try:
        dates = dates_fn(sup)
    except Exception:
        dates = []
    _, days_to = next_earnings_est(dates, today)
    try:
        entry = date.fromisoformat(idea["entry"]) if idea.get("entry") else None
    except ValueError:
        entry = None
    rse = reported_since_entry(dates, entry, today) if entry else False

    return {"borrow": borrow, "earnings": {"days_to": days_to, "reported_since_entry": rse},
            "liquidity": liquidity}


def narrate(idea: dict, facts: dict) -> str:
    """One Opus sentence from the computed facts; adds no numbers. '' on any error (fail soft)."""
    prompt = (f"Idea: supplier {idea['supplier']} vs customer {idea['customer']}. Risk facts:\n"
              f"{json.dumps(facts)}\n"
              "Write one short sentence on borrow / earnings-timing / liquidity risk. If borrow "
              "class is 'hard', note the short can still be put on via options (a put spread).")
    try:
        return complete(prompt, model=OPUS, system=_NARRATE_SYS, max_tokens=256).strip()
    except Exception:
        return ""


def build_risk(state: dict) -> dict:
    per = {}
    for o in state.get("open", []):
        try:
            facts = assess_idea_risk(o)
            facts["note"] = narrate(o, facts)
        except Exception:
            facts = {"borrow": {"ticker": None, "class": "na"},
                     "earnings": {"days_to": None, "reported_since_entry": False},
                     "liquidity": "ok", "note": ""}
        per[f'{o["supplier"]}|{o["customer"]}'] = facts
    return {"generated_utc": datetime.now(timezone.utc).isoformat(), "model_used": OPUS,
            "per_idea": per}


def risk_flag(rv: dict | None) -> str:
    """Short reader-facing flag, shared by dashboard + email. Precedence: borrow > earnings > liq."""
    if not rv:
        return ""
    if (rv.get("borrow") or {}).get("class") == "hard":
        return "⚠ hard to borrow — short via options"
    if (rv.get("earnings") or {}).get("reported_since_entry"):
        return "⚠ post-earnings (edge likely spent)"
    if rv.get("liquidity") == "thin":
        return "⚠ thin liquidity"
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_risk -v`
Expected: PASS (Task 2 + 6 new = 9 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/risk.py tests/test_risk.py
git commit -m "feat(risk): assess_idea_risk + narrate + build_risk + risk_flag"
```

---

### Task 4: `risk.py` entry + pipeline wiring

**Files:**
- Create: `risk.py`
- Modify: `run_paper.sh` (insert `risk.py` after `catalyst.py`, before `digest.py`); `.gitignore` (ignore `risk.json`)
- Test: `tests/test_risk_entry.py`

**Interfaces:**
- Consumes: `elp.risk.build_risk`.
- Produces: `risk.json`, gitignored. Fail-soft entry.

- [ ] **Step 1: Write the failing test** (`tests/test_risk_entry.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_risk_entry -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'risk'`

- [ ] **Step 3: Write minimal implementation** (`risk.py`)

```python
"""Daily Risk/Borrow pass: per open idea, deterministic borrow / earnings-window / liquidity
facts with a thin Opus note. Writes risk.json (consumed by digest.py / dashboard.py /
email_report.py). Fails SOFT so the pipeline never breaks.

Run: python3 risk.py
"""
import json

from elp.risk import build_risk

STATE, OUT = "paper_state.json", "risk.json"


def main() -> None:
    try:
        state = json.load(open(STATE))
    except FileNotFoundError:
        print(f"[risk] no {STATE} yet — run track.py first; skipping")
        return
    if not state.get("open"):
        print("[risk] no open ideas; skipping")
        return
    try:
        r = build_risk(state)
    except Exception as e:                    # no key / API / network -> fail soft
        print(f"[risk] skipped ({type(e).__name__}: {e})")
        return
    json.dump(r, open(OUT, "w"), indent=1)
    print(f"wrote {OUT} | {len(r['per_idea'])} ideas assessed | model={r['model_used']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_risk_entry -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire the pipeline + gitignore**

Edit `run_paper.sh` — insert the risk line between the catalyst and digest lines:

```bash
python3 catalyst.py  >> paper_run.log 2>&1   # News/Catalyst ensemble -> catalyst.json (fails soft)
python3 risk.py      >> paper_run.log 2>&1   # Risk/Borrow facts -> risk.json (fails soft)
python3 digest.py    >> paper_run.log 2>&1   # Fable-5 digest; consumes catalyst.json + risk.json
```

Append to `.gitignore` (generated, like `catalyst.json`):

```
risk.json
```

- [ ] **Step 6: Commit**

```bash
git add risk.py tests/test_risk_entry.py run_paper.sh .gitignore
git commit -m "feat(risk): daily entry + pipeline wiring (catalyst->risk->digest)"
```

---

### Task 5: Digest soft-derate — consume risk verdicts

**Files:**
- Modify: `elp/digest.py` (`_prompt` + `build_digest` gain an optional `risk` map)
- Modify: `digest.py` (load `risk.json`, pass it in)
- Test: `tests/test_digest.py` (add a case)

**Interfaces:**
- Consumes: `risk.json` `per_idea` keyed `"SUP|CUST"` with `{borrow:{class}, earnings:{reported_since_entry}, liquidity}`.
- Produces: `_prompt(state, notes, catalyst=None, risk=None)`, `build_digest(state, notes, catalyst=None, risk=None)` — backward compatible.

- [ ] **Step 1: Write the failing test** (add to `tests/test_digest.py` `TestPrompt`)

```python
    def test_prompt_includes_risk_when_supplied(self):
        risk = {"SWKS|AAPL": {"borrow": {"class": "hard"},
                              "earnings": {"reported_since_entry": True}, "liquidity": "thin"}}
        p = _prompt(STATE, NOTES, None, risk)
        self.assertIn("borrow=hard", p)
        self.assertIn("earnings=post-earnings", p)
        self.assertIn("liq=thin", p)
        self.assertIn("options", p.lower())      # instruction mentions the options fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_digest -v`
Expected: FAIL — `_prompt() takes from 2 to 3 positional arguments but 4 were given`

- [ ] **Step 3: Write minimal implementation** (edit `elp/digest.py`)

Replace the current `_prompt` with this (adds the `risk` param, the `rtag`, and the extended ranking instruction):

```python
def _prompt(state: dict, notes: dict, catalyst: dict | None = None, risk: dict | None = None) -> str:
    catalyst = catalyst or {}
    risk = risk or {}
    lines = ["Open paper trades (supplier <- principal customer | kind | days held | link | catalyst | risk):"]
    for o in state.get("open", []):
        note = notes.get((o["supplier"], o["customer"]), "")
        kind = o.get("kind", "LONG" if o.get("side", 0) > 0 else "SHORT")
        key = f'{o["supplier"]}|{o["customer"]}'
        cv = catalyst.get(key)
        ctag = (f' | catalyst={cv.get("customer_catalyst", "?")}, '
                f'confounded={cv.get("confounding", "?")}') if cv else ""
        rv = risk.get(key)
        rtag = ""
        if rv:
            b = (rv.get("borrow") or {}).get("class", "?")
            e = "post-earnings" if (rv.get("earnings") or {}).get("reported_since_entry") else "ok"
            rtag = f' | borrow={b}, earnings={e}, liq={rv.get("liquidity", "?")}'
        lines.append(f'- {o["supplier"]} <- {o["customer"]} | {kind} | {o["days"]}d | {note}{ctag}{rtag}')
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
        '"none" or confounded="yes", whose borrow=hard (note the short can still go on via options), '
        'whose earnings=post-earnings (the lead-lag edge fades after the supplier reports), or whose '
        'liq=thin — and say so in its rationale. Use only the tickers listed above. Do NOT return a '
        "separate watch list."
    )
    return "\n".join(lines)
```

Change `build_digest` to accept and forward `risk`:

```python
def build_digest(state: dict, notes: dict, catalyst: dict | None = None,
                 risk: dict | None = None) -> dict:
    text, model = complete_fallback(_prompt(state, notes, catalyst, risk), primary=PRIMARY,
                                    fallback=FALLBACK, system=SYSTEM, max_tokens=4096)
```

(Leave the rest of `build_digest` unchanged.)

- [ ] **Step 4: Load risk.json in the entry** (edit `digest.py`)

After the existing `catalyst.json` load block, add a `risk.json` load and pass both to `build_digest`:

```python
    risk = {}
    try:
        risk = json.load(open("risk.json")).get("per_idea", {})
    except (FileNotFoundError, ValueError):
        pass
    try:
        d = build_digest(state, notes, catalyst, risk)
    except Exception as e:                    # no key / API / network -> fail soft
        print(f"[digest] skipped ({type(e).__name__}: {e}) — dashboard keeps prior digest")
        return
```

(Replace the existing `d = build_digest(state, notes, catalyst)` call; keep the rest.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_digest -v`
Expected: PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
git add elp/digest.py digest.py tests/test_digest.py
git commit -m "feat(digest): soft-derate ideas by risk verdict (borrow/earnings/liquidity)"
```

---

### Task 6: Show the risk flag on the dashboard + email

**Files:**
- Modify: `dashboard.py` (`idea_row(o, catalyst=None, risk=None)`; `build` loads `risk.json`)
- Modify: `email_report.py` (`render` loads `risk.json`; combine risk into the idea flag)
- Test: `tests/test_dashboard.py`, `tests/test_email_report.py`

**Interfaces:**
- Consumes: `elp.risk.risk_flag`, `risk.json` `per_idea`.
- Produces: `idea_row(o, catalyst=None, risk=None)` (backward compatible).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard.py` `TestIdeaRow`:

```python
    def test_row_shows_risk_flag_when_supplied(self):
        html = idea_row(IDEA, None, {"borrow": {"class": "hard"}})
        self.assertIn("hard to borrow", html)
```

Add to `tests/test_email_report.py` a new method in `TestRender`:

```python
    def test_risk_flag_appears_when_risk_json_present(self):
        import email_report, json, os, shutil
        cwd = os.getcwd(); tmp = os.path.join(os.path.dirname(__file__), "_emailrisk")
        os.makedirs(tmp, exist_ok=True); os.chdir(tmp)
        try:
            json.dump({"per_idea": {"GILD|CAH": {"borrow": {"class": "hard"}}}},
                      open("risk.json", "w"))
            html, text = email_report.render(STATE, None)
            self.assertIn("hard to borrow", html)
        finally:
            os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard tests.test_email_report -v`
Expected: FAIL — `idea_row() takes from 1 to 2 positional arguments but 3 were given`; email test fails (no flag).

- [ ] **Step 3: Implement dashboard** (edit `dashboard.py`)

Add import near the other `elp` imports: `from elp.risk import risk_flag`. Change `idea_row` to take `risk` and show both flags (replace the two `flag`/`fhtml` lines):

```python
def idea_row(o, catalyst=None, risk=None):
    """One idea as an HTML row: net direction + both legs + expression + catalyst/risk flags."""
    direction = "LONG" if o["side"] > 0 else "SHORT"
    cap = "$10k hard" if o.get("risk_cap") == "hard" else "~$10k stop (gap risk)"
    rcls = "pos" if o["ret"] > 0 else "neg"
    flags = [f for f in (catalyst_flag(catalyst), risk_flag(risk)) if f]
    fhtml = "".join(f"<br><span class=sub>{escape(f)}</span>" for f in flags)
```

(Keep the rest of `idea_row`'s `return (...)` exactly as-is — it already uses `fhtml`.)

In `build()`, after the existing `catalyst.json` load, add a `risk.json` load and pass it to `idea_row` (replace the `open_rows = ...` line):

```python
    try:
        rsk = json.load(open("risk.json")).get("per_idea", {})
    except (FileNotFoundError, ValueError):
        rsk = {}
    open_rows = "".join(
        idea_row(o, cat.get(f'{o["supplier"]}|{o["customer"]}'),
                 rsk.get(f'{o["supplier"]}|{o["customer"]}')) for o in s["open"]) or \
        "<tr><td colspan=7 class=muted>no open ideas</td></tr>"
```

- [ ] **Step 4: Implement email** (edit `email_report.py`)

Add import: `from elp.risk import risk_flag`. After the existing `catalyst.json` load block in `render`, add a `risk.json` load:

```python
    try:
        rsk = json.load(open("risk.json")).get("per_idea", {})
    except (FileNotFoundError, ValueError):
        rsk = {}
```

Change the per-idea `flag = ...` line to combine catalyst + risk (the HTML row and text line already consume `flag`):

```python
        key = f'{o["supplier"]}|{o["customer"]}'
        flag = " · ".join(f for f in (catalyst_flag(cat.get(key)), risk_flag(rsk.get(key))) if f)
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: OK (all tests, including the new dashboard/email risk cases).

- [ ] **Step 6: Commit**

```bash
git add dashboard.py email_report.py tests/test_dashboard.py tests/test_email_report.py
git commit -m "feat(ui): show risk flag on dashboard + email"
```

---

## Verification (whole feature, end-to-end)

1. **Full offline suite green:** `python3 -m unittest discover -s tests` → OK.
2. **Live smoke (spends a few cents; authorized like the digest/catalyst runs):**
   - `python3 track.py` then `python3 risk.py` → prints `wrote risk.json | N ideas assessed`; open `risk.json` and confirm each idea has `borrow`/`earnings`/`liquidity` facts + a one-line `note`. Sanity-check: SPY-hedged shorts → `borrow.class` `na`/`easy`; a small-cap counterpart short → `hard`.
   - `python3 digest.py` → runs; `python3 dashboard.py` → the Daily read down-ranks hard-borrow / post-earnings / thin ideas, and each Open-trades row shows its risk flag beside the catalyst flag.
   - `EMAIL_DRYRUN=1 python3 email_report.py` → `email_report.eml` shows the risk flag on each idea line.
3. **Fail-soft check:** temporarily rename `.tiingo_token`/`.anthropic_key`, run `python3 risk.py` → prints `[risk] skipped ...`, exits 0, writes nothing; `digest.py`/`dashboard.py` still run. Restore.

## Self-Review

**Spec coverage:** §3.1 Tiingo helpers → Task 1. §3.2 pure fns → Task 2; orchestration/narrate/build/flag → Task 3. §3.3 entry → Task 4. §4 soft-derate wiring → Tasks 4-6. §5 degradation → fail-soft in Tasks 1,3,4 + verification step 3. §6 testing → tests in every task. §7 cost → documented (no code). §8 out-of-scope → honored (no engine change; borrow is a proxy; no greeks).

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** verdict keys consistent — `borrow.class`, `earnings.reported_since_entry`, `earnings.days_to`, `liquidity` written by `assess_idea_risk`/`build_risk` (Task 3) and read by `risk_flag` (Task 3), `_prompt` (Task 5), and the UI (Task 6). `per_idea` keys are `"SUP|CUST"` everywhere. `borrow_class`/`next_earnings_est`/`reported_since_entry` signatures (Task 2) match their calls in `assess_idea_risk` (Task 3). `idea_row(o, catalyst=None, risk=None)` stays compatible with the existing 1- and 2-arg calls/tests.

## Out of scope (deliberately)
- Real borrow-fee / short-interest data and exact earnings dates (proxy + cadence estimate only).
- Any engine open/close change (soft-derate only); options-overlay synthetic-short sizing (PLAN §11, gated on Phase 5); greeks/theta risk.
