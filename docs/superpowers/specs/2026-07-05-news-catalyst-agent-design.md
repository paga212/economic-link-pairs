# News/Catalyst agent — design

**Status:** design approved 2026-07-05 (brainstormed with Pierre).
**Builds on:** the live paper-trade (`track.py` → `paper_state.json`), the Fable-5 digest
(`elp/digest.py`, `digest.py`), and the LLM client (`elp/llm.py`). Implements the Phase-3
News/Catalyst Agent from `PLAN.md` §3 (Opus 4.8).

## 1. Context and goal

For each open idea, confirm that a **genuine customer information event** drove the signal,
and rule out **confounding supplier-specific news** already priced into the supplier. The
verdict **soft-derates** ideas in the daily read: it never changes which trades the
deterministic engine opens or closes (recommendations only), it only informs the Fable-5
Master ranking and is shown to the reader.

Constraint discovered in exploration: `elp/llm.py` is a bare messages call with no web
access, and the model's training cutoff means it does **not** know a recent customer move on
its own. So current news must be fetched and fed in. Per Pierre's choice this uses a
**three-source ensemble reconciled by a master** (council of agents), honoring his stated
methodology.

## 2. Architecture — three source-agents + a reconciler (per open idea)

```
customer & supplier headlines ─┬─ rss_agent    ─┐
                               ├─ tiingo_agent ─┼─ reconcile (master) → verdict → digest soft-derate + dashboard/email
                               └─ web_agent    ─┘
```

All agents are **Opus 4.8** (PLAN §3/§5). Code fetches; the LLM only reasons (PLAN §2): no
agent computes a number.

## 3. Components (each isolated and independently testable)

### 3.1 `elp/news.py` — deterministic fetchers (no LLM)
- `google_rss(query: str, days: int = 30) -> list[dict]` — `urllib` GET of
  `news.google.com/rss/search?q=<query>+when:<days>d`, parsed with stdlib `xml.etree`.
- `tiingo_news(tickers: str, start: str | None = None, end: str | None = None, limit: int = 20) -> list[dict]`
  — Tiingo `/tiingo/news` JSON, reusing the existing token loader; date-windowed to the idea's
  entry neighbourhood.
- Both return `[{title, source, date, url}]` and **fail soft to `[]`** on any network/parse
  error (a dead source must never crash the run).

### 3.2 `elp/llm.py` — add web-search support
- Add an optional `tools` path to `complete()` (or a thin `complete_search()`): send
  `tools=[{"type": "web_search_20250305", "name": "web_search"}]` and extract the final text
  from the response (the server tool auto-executes; no client tool loop). **Availability is
  unconfirmed on this API plan — probe first.** If it 4xx-rejects, `web_agent` degrades to
  `unavailable` and the ensemble runs on the two deterministic sources.

### 3.3 `elp/catalyst.py` — the agent fleet + reconciler
- **Source-agent** (`_source_verdict(source, evidence, idea) -> dict`): one Opus call that, given
  that source's customer+supplier headlines (or, for `web_agent`, a live web search), returns
  `{customer_catalyst: "confirmed"|"weak"|"none", catalyst_note, confounding_supplier_news:
  "yes"|"no", confounding_note}`. A source that errors or returns no evidence yields
  `{... "unknown" ...}` rather than raising.
- Three thin wrappers — `rss_agent(idea)`, `tiingo_agent(idea)`, `web_agent(idea)` — differing
  only in how evidence is obtained (RSS fetch / Tiingo fetch / web-search call).
- **`reconcile(idea, verdicts) -> dict`**: one master Opus call given the three source verdicts;
  returns the final `{customer_catalyst, confounding, note, confidence: "high"|"med"|"low"}`,
  weighing agreement, currency, and relevance. Works with as few as one non-`unknown` verdict.
- `assess_idea(idea) -> dict` orchestrates the three + reconcile.
- `build_catalyst(state) -> dict` → `{generated_utc, model_used, per_idea: {(supplier,customer):
  verdict}}` for every open idea.

### 3.4 `catalyst.py` — top-level entry (mirrors `digest.py`)
Reads `paper_state.json`, runs `build_catalyst`, writes `catalyst.json` (generated + gitignored).
**Fail soft:** no key / API error / no open ideas → warn, write nothing, exit 0 so the pipeline
never breaks.

## 4. Soft-derate wiring
- `run_paper.sh`: insert `python3 catalyst.py` **before** `python3 digest.py`.
- `elp/digest.py`: `_prompt` gains an optional catalyst map; each idea's verdict is included so
  Fable-5 **down-ranks** `none`/confounded ideas and states why. `digest.py` loads `catalyst.json`
  if present and passes it in. Absent → unchanged behaviour.
- `dashboard.py` / `email_report.py`: show a per-idea catalyst flag — `catalyst: confirmed`,
  `⚠ no clear catalyst`, or `⚠ confounded (supplier news)`.

## 5. Error handling / degradation
Every layer fails soft: a dead source → `[]` → that agent → `unknown`; web search unavailable →
two-source ensemble; whole step down → `digest.py` still runs without catalyst context. Numbers
never come from an agent; the reconciler emits only labels + prose.

## 6. Testing (offline, stdlib)
- `tests/test_news.py`: `google_rss` parses a canned RSS document and `tiingo_news` a canned
  JSON body (both via monkeypatched `urllib.request.urlopen`); network error → `[]`.
- `tests/test_catalyst.py` (monkeypatch the LLM, like `test_digest.py`): a source-agent prompt
  includes the fetched headlines; `reconcile` merges three verdicts into one; `assess_idea`
  degrades when a source is `unknown`; `build_catalyst` covers every open idea.
- `tests/test_digest.py`: extend so the prompt carries catalyst context when supplied.

## 7. Cost
~4 Opus calls per idea (3 source-agents + reconcile) ⇒ ~24 calls/day on a 6-idea book, plus
web-search fees — a few dollars/day, within PLAN §8. Materially more than a single-source
annotation; the price of the chosen ensemble. Per-idea prompts (not batched) for focus;
batching is a later optimization if cost matters.

## 8. Out of scope
- Any change to how trades are opened/closed (soft-derate only; hard catalyst-gating is reserved
  for the deferred options overlay, PLAN §11.1 Gate B).
- Historical backfill of catalysts for already-closed trades.
- A paid news feed; sentiment scoring; per-source model tuning.
