# Link Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `validate_links` — a per-link guard that quarantines bad customer-supplier links (wrong-ticker resolution and glitchy/illiquid price data) — plus a standalone cleanup entry and a durable hook in the Phase-B build.

**Architecture:** One new pure-ish module `elp/linkcheck.py` (three cheap checks + `validate_links`, dependency-injected for offline tests), a thin `linkcheck.py` entry that runs it on the current `universe_links.json`, and a two-line hook in `phase_b_build.py`. Reuses existing liquidity (`elp/liquidity.py`), price bars (`elp/tiingo.py::fetch_daily_bars`), and the SEC map/name-normalizer (`elp/edgar.py`).

**Tech Stack:** Python 3, standard library only (`difflib`, `json`, `urllib` via edgar). No new dependencies.

## Global Constraints

- **stdlib only** — no third-party deps. Reuse `elp/edgar.py` (`load_ticker_map`, `norm`), `elp/liquidity.py` (`is_tradeable`, `dollar_adv`), `elp/tiingo.py` (`fetch_daily_bars`).
- **Offline tests** — `validate_links` takes injectable `bars_fn` and `ticker_map`; unit tests pass stubs and never hit the network.
- **Quarantine, never silent-drop** — rejected links go to `rejected_links.json` with a `reason`; print a one-line summary.
- **Frozen config constants:** `GAP_MAX = 5.0`, `NAME_SIM_MIN = 0.6`, `AMBIG_MAX = 3`. Do not tune on live outcomes.
- **Determinism** — same inputs → same (good, rejected) partition.
- **Prerequisite:** the `expression-engine` branch (provides `elp/liquidity.py` + `fetch_daily_bars`). This branch is stacked on it.
- **Reference for exact behavior:** `docs/superpowers/specs/2026-07-05-link-validation-design.md`.

---

### Task 1: Price-sanity check

**Files:**
- Create: `elp/linkcheck.py` (module header + constants + `_price_ok`)
- Test: `tests/test_linkcheck.py`

**Interfaces:**
- Produces: `_price_ok(bars) -> tuple[bool, str]` — `(True, "")` if the `(date,price,volume)` series is tradeable (via `is_tradeable`) and has no adjacent-bar ratio above `GAP_MAX`; else `(False, reason)` with reason in `{"no_data","illiquid","bad_bars"}`.

- [ ] **Step 1: Write the failing test** (`tests/test_linkcheck.py`)

```python
"""Offline unit tests for link validation (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.linkcheck import _price_ok  # noqa: E402


def bars(prices, vol=1_000_000.0, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), float(p), vol) for i, p in enumerate(prices)]


class TestPriceOk(unittest.TestCase):
    def test_clean_liquid_series_ok(self):
        ok, reason = _price_ok(bars([50] * 63))          # $50, $50M ADV
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_empty_series(self):
        self.assertEqual(_price_ok([]), (False, "no_data"))

    def test_penny_or_illiquid(self):
        self.assertEqual(_price_ok(bars([0.07] * 63))[1], "illiquid")   # sub-$5

    def test_glitch_bar_flagged(self):
        # a $0.07 bar among $115 bars -> >5x adjacent jump (the MZTI case)
        px = [115] * 30 + [0.07] + [115] * 32
        self.assertEqual(_price_ok(bars(px))[1], "bad_bars")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_linkcheck -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elp.linkcheck'`

- [ ] **Step 3: Write minimal implementation** (`elp/linkcheck.py`)

```python
"""Validate customer-supplier links: quarantine wrong-ticker resolutions and glitchy/illiquid
price data before they reach the live universe. Reuses the liquidity gate, price bars, and the
SEC ticker map. Dependency-injected so unit tests run offline. Pure stdlib.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from elp.edgar import load_ticker_map, norm
from elp.liquidity import is_tradeable
from elp.tiingo import fetch_daily_bars

GAP_MAX = 5.0        # max adjacent-bar price ratio before a series is "glitchy"
NAME_SIM_MIN = 0.6   # difflib ratio floor for customer_raw vs the ticker's real title
AMBIG_MAX = 3        # max SEC titles a customer_raw may match before it's "ambiguous"


def _price_ok(bars) -> tuple[bool, str]:
    """(ok, reason) for a (date,price,volume) series: tradeable and free of absurd jumps."""
    if not bars:
        return False, "no_data"
    if not is_tradeable(bars):
        return False, "illiquid"
    for i in range(1, len(bars)):
        p0, p1 = bars[i - 1][1], bars[i][1]
        if p0 > 0 and p1 > 0 and (p1 / p0 > GAP_MAX or p0 / p1 > GAP_MAX):
            return False, "bad_bars"
    return True, ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_linkcheck -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/linkcheck.py tests/test_linkcheck.py
git commit -m "feat(linkcheck): _price_ok — liquidity + glitch-bar detection"
```

---

### Task 2: Name↔ticker check

**Files:**
- Modify: `elp/linkcheck.py` (add `_name_ok`)
- Test: `tests/test_linkcheck.py` (add a class)

**Interfaces:**
- Produces: `_name_ok(ticker, raw, ticker_to_title, title_token_sets) -> tuple[bool, str]` where `ticker_to_title` is `{ticker: title}` and `title_token_sets` is `list[set[str]]` (normalized token-sets of every title). Reason in `{"unknown_ticker","ambiguous","name_mismatch"}`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_linkcheck.py`)

```python
from elp.linkcheck import _name_ok  # noqa: E402


class TestNameOk(unittest.TestCase):
    # Stub SEC universe: SNX + Walmart are unique; three "Alpha ..." names make "Alpha" ambiguous.
    T2T = {"SNX": "TD SYNNEX Corporation", "WMT": "Walmart Inc.",
           "ATGL": "Alpha Technology Group Ltd", "AMR": "Alpha Metallurgical Resources Inc",
           "AOSL": "Alpha and Omega Semiconductor Ltd", "APT": "Alpha Pro Tech Ltd"}
    TOKS = [set(norm(t).split()) for t in T2T.values()]

    def test_unambiguous_match_ok(self):
        self.assertEqual(_name_ok("SNX", "TD Synnex Corporation", self.T2T, self.TOKS), (True, ""))
        self.assertEqual(_name_ok("WMT", "Walmart Inc.", self.T2T, self.TOKS), (True, ""))

    def test_generic_name_is_ambiguous(self):     # the NRP->ATGL case
        ok, reason = _name_ok("ATGL", "Alpha", self.T2T, self.TOKS)
        self.assertFalse(ok)
        self.assertEqual(reason, "ambiguous")

    def test_unknown_ticker(self):
        self.assertEqual(_name_ok("ZZZZ", "Whatever", self.T2T, self.TOKS)[1], "unknown_ticker")

    def test_name_mismatch(self):
        # ticker exists and raw is specific, but its real title is unrelated
        ok, reason = _name_ok("SNX", "Nvidia Corporation", self.T2T, self.TOKS)
        self.assertEqual((ok, reason), (False, "name_mismatch"))
```

Note: with `AMBIG_MAX=3`, four "Alpha …" titles each contain the token `alpha`, so `{"alpha"}` matches 4 > 3 → ambiguous.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_linkcheck -v`
Expected: FAIL — `ImportError: cannot import name '_name_ok'`

- [ ] **Step 3: Write minimal implementation** (append to `elp/linkcheck.py`)

```python
def _name_ok(ticker, raw, ticker_to_title, title_token_sets) -> tuple[bool, str]:
    """(ok, reason) for the customer name<->ticker mapping. Rejects unknown tickers, generic
    names that match many companies (ambiguous), and titles unrelated to the extracted name."""
    if ticker not in ticker_to_title:
        return False, "unknown_ticker"
    raw_tokens = set(norm(raw).split())
    if not raw_tokens:
        return False, "ambiguous"
    matches = sum(1 for toks in title_token_sets if raw_tokens <= toks)
    if matches > AMBIG_MAX:
        return False, "ambiguous"
    sim = SequenceMatcher(None, norm(raw), norm(ticker_to_title[ticker])).ratio()
    if sim < NAME_SIM_MIN:
        return False, "name_mismatch"
    return True, ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_linkcheck -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/linkcheck.py tests/test_linkcheck.py
git commit -m "feat(linkcheck): _name_ok — existence + ambiguity + consistency"
```

---

### Task 3: `validate_links`

**Files:**
- Modify: `elp/linkcheck.py` (add `validate_links`)
- Test: `tests/test_linkcheck.py` (add a class)

**Interfaces:**
- Produces: `validate_links(links, bars_fn=fetch_daily_bars, ticker_map=None) -> tuple[list, list]`. `links` are `universe_links.json` dicts (`{supplier, customer, customer_raw, …}`). Returns `(good, rejected)`; each rejected dict is the original link plus `"reason"`. Supplier price failure → `"supplier_<reason>"`, customer price failure → `"customer_<reason>"`, name failure → the bare name reason. `ticker_map` is `(by_cik, by_name)` from `edgar.load_ticker_map()`; `None` loads it.

- [ ] **Step 1: Write the failing test** (append to `tests/test_linkcheck.py`)

```python
from elp.linkcheck import validate_links  # noqa: E402


class TestValidateLinks(unittest.TestCase):
    def _map(self):
        t2t = {"SNX": "TD SYNNEX Corporation", "WMT": "Walmart Inc.", "ADSK": "Autodesk Inc",
               "MZTI": "Mozzarti Inc", "NRP": "Natural Resource Partners LP",
               "ATGL": "Alpha Technology Group Ltd", "AMR": "Alpha Metallurgical Resources Inc",
               "AOSL": "Alpha and Omega Semiconductor Ltd", "APT": "Alpha Pro Tech Ltd"}
        by_cik = {i: {"ticker": tk, "title": ti} for i, (tk, ti) in enumerate(t2t.items())}
        return (by_cik, {})

    def _bars_fn(self, t):
        good = bars([50] * 63)
        glitch = bars([115] * 30 + [0.07] + [115] * 32)   # MZTI glitch
        return {"ADSK": good, "SNX": good, "MZTI": glitch, "WMT": good,
                "NRP": good, "ATGL": good}.get(t, good)

    def test_keeps_good_rejects_bad(self):
        links = [
            {"supplier": "ADSK", "customer": "SNX", "customer_raw": "TD Synnex Corporation"},
            {"supplier": "MZTI", "customer": "WMT", "customer_raw": "Walmart Inc."},   # supplier glitch
            {"supplier": "NRP", "customer": "ATGL", "customer_raw": "Alpha"},           # ambiguous
        ]
        good, rejected = validate_links(links, bars_fn=self._bars_fn, ticker_map=self._map())
        self.assertEqual([g["supplier"] for g in good], ["ADSK"])
        reasons = {r["supplier"]: r["reason"] for r in rejected}
        self.assertEqual(reasons["MZTI"], "supplier_bad_bars")
        self.assertEqual(reasons["NRP"], "ambiguous")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_linkcheck -v`
Expected: FAIL — `ImportError: cannot import name 'validate_links'`

- [ ] **Step 3: Write minimal implementation** (append to `elp/linkcheck.py`)

```python
def validate_links(links, bars_fn=fetch_daily_bars, ticker_map=None) -> tuple[list, list]:
    """Partition links into (good, rejected). Each rejected link carries a 'reason'. Checks:
    supplier price-sanity, customer price-sanity, then customer name<->ticker (first failure wins)."""
    if ticker_map is None:
        ticker_map = load_ticker_map()
    by_cik, _ = ticker_map
    ticker_to_title = {v["ticker"]: v["title"] for v in by_cik.values()}
    title_token_sets = [set(norm(t).split()) for t in ticker_to_title.values()]

    cache: dict = {}
    def _bars(t):
        if t not in cache:
            try:
                cache[t] = bars_fn(t)
            except Exception:
                cache[t] = []
        return cache[t]

    good, rejected = [], []
    for lk in links:
        ok, reason = _price_ok(_bars(lk["supplier"]))
        if not ok:
            rejected.append({**lk, "reason": f"supplier_{reason}"}); continue
        ok, reason = _price_ok(_bars(lk["customer"]))
        if not ok:
            rejected.append({**lk, "reason": f"customer_{reason}"}); continue
        ok, reason = _name_ok(lk["customer"], lk.get("customer_raw", ""),
                              ticker_to_title, title_token_sets)
        if not ok:
            rejected.append({**lk, "reason": reason}); continue
        good.append(lk)
    return good, rejected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_linkcheck -v` then `python3 -m unittest discover -s tests`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add elp/linkcheck.py tests/test_linkcheck.py
git commit -m "feat(linkcheck): validate_links partitions good/rejected with reasons"
```

---

### Task 4: `linkcheck.py` standalone entry

**Files:**
- Create: `linkcheck.py` (top-level, mirrors `track.py`)

**Interfaces:**
- Consumes: `validate_links` (Task 3). Reads `universe_links.json`, writes the cleaned file back plus `rejected_links.json`, prints a summary. No unit test (thin I/O wrapper; exercised by the live cleanup run in Verification).

- [ ] **Step 1: Write the implementation** (`linkcheck.py`)

```python
"""Validate universe_links.json in place: keep good links, quarantine bad ones to
rejected_links.json (with reasons). Run the one-time cleanup or any re-check.

Run: python3 linkcheck.py
"""
import json
from collections import Counter

from elp.linkcheck import validate_links

IN, REJ = "universe_links.json", "rejected_links.json"


def main() -> None:
    links = json.load(open(IN))
    good, rejected = validate_links(links)
    json.dump(good, open(IN, "w"), indent=1)
    json.dump(rejected, open(REJ, "w"), indent=1)
    reasons = dict(Counter(r["reason"] for r in rejected))
    print(f"kept {len(good)}/{len(links)} | rejected {len(rejected)}: {reasons}")
    for r in rejected:
        print(f"  drop {r['supplier']}->{r['customer']} ({r.get('customer_raw','')}): {r['reason']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Byte-compile check**

Run: `python3 -m py_compile linkcheck.py`
Expected: no output (clean).

- [ ] **Step 3: Commit**

```bash
git add linkcheck.py
git commit -m "feat: linkcheck.py entry — clean universe_links.json, quarantine rejects"
```

---

### Task 5: Durable guard in `phase_b_build.py`

**Files:**
- Modify: `phase_b_build.py` (validate before writing `universe_links.json`)

**Interfaces:**
- Consumes: `validate_links` (Task 3) and the `(by_cik, by_name)` already loaded at the top of `phase_b_build.main`.

- [ ] **Step 1: Apply the change**

In `phase_b_build.py::main`, the current tail is:
```python
    uniq = {(x["supplier"], x["customer"]): x for x in links}
    out = sorted(uniq.values(), key=lambda z: z["supplier"])
    json.dump(out, open(OUT, "w"), indent=1)
```
Replace the `json.dump(out, ...)` line with a validate step that reuses the already-loaded map:
```python
    from elp.linkcheck import validate_links
    out, rejected = validate_links(out, ticker_map=(by_cik, by_name))
    json.dump(out, open(OUT, "w"), indent=1)
    json.dump(rejected, open("rejected_links.json", "w"), indent=1)
    print(f"validated: kept {len(out)}, quarantined {len(rejected)} -> rejected_links.json")
```
(`by_cik`, `by_name` are already in scope from `load_ticker_map()` at the top of `main`. Everything below — the `named`/summary prints — operates on the now-validated `out`.)

- [ ] **Step 2: Byte-compile check**

Run: `python3 -m py_compile phase_b_build.py`
Expected: no output (clean).

- [ ] **Step 3: Commit**

```bash
git add phase_b_build.py
git commit -m "feat(phase_b): validate links before writing the universe (durable guard)"
```

---

## Verification (live, controller-run — not a unit test)

1. Full offline suite: `python3 -m unittest discover -s tests` → all pass (existing + new `test_linkcheck`).
2. **One-time cleanup:** with `.tiingo_token` present, run `python3 linkcheck.py`. Confirm the summary shows `NRP->ATGL` rejected (`ambiguous`) and `MZTI->WMT` rejected (`supplier_bad_bars`); scan `rejected_links.json` for false positives among the other 24 (tune `AMBIG_MAX`/`NAME_SIM_MIN`/`GAP_MAX` or whitelist only if a clearly-good link was dropped).
3. Confirm `universe_links.json` shrank to the good links; `git diff` it and commit both `universe_links.json` and `rejected_links.json`.
4. Sanity: `python3 track.py` runs on the cleaned universe without the MZTI/ATGL names.

## Self-Review

**Spec coverage:** §2 checks → Tasks 1 (price) + 2 (name) + 3 (combine). §3 name mechanics (existence/ambiguity/consistency, edgar reuse) → Task 2. §4 handling + callers → Tasks 3 (function), 4 (standalone), 5 (phase_b guard); `load_universe` untouched (correct — no task changes it). §5 one-time cleanup → Verification step 2. §6 config constants → Task 1 (defined). §7 offline tests → Tasks 1–3.
**Placeholder scan:** none — every code step is concrete.
**Type consistency:** `_price_ok(bars)->(bool,str)` and `_name_ok(ticker,raw,ticker_to_title,title_token_sets)->(bool,str)` are produced in Tasks 1–2 and consumed in Task 3 exactly; `validate_links(links,bars_fn,ticker_map)->(good,rejected)` consumed by Tasks 4–5. `ticker_map=(by_cik,by_name)` shape matches `edgar.load_ticker_map`.

## Out of scope
- Repairing bad bars / auto-correcting wrong tickers (reject only).
- Supplier name↔ticker validation (supplier ticker is reliable from filing metadata).
- Re-running Phase-B LLM extraction.
