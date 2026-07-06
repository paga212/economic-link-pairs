# Risk/Borrow agent — design

**Status:** design approved 2026-07-05 (brainstormed with Pierre).
**Builds on:** the live paper-trade (`track.py` → `paper_state.json`), `elp/liquidity.py`
(`dollar_adv`, `is_tradeable`, `beta`), `elp/tiingo.py` (token + `_fetch`), the Fable-5 digest,
and the News/Catalyst agent's fail-soft / soft-derate pattern. Implements the Phase-3
Risk/Borrow agent from `PLAN.md` §3 (Opus 4.8 + tools).

## 1. Context and goal

For each open idea, judge tradeability along three axes and **soft-derate** risky ideas in the
daily read (never changes engine open/close — recommendations only):
1. **Borrow** — is the short *stock* leg hard to borrow? (Only long-idea neutralizers are short
   stock; primary shorts are already bear-put-spreads, which need no borrow.)
2. **Earnings-window timing (Madsen 2017)** — the lead-lag edge concentrates *before* the
   supplier's own earnings and dissipates after. Flag ideas where the supplier likely already
   reported since entry.
3. **Liquidity** — has the supplier thinned below the tradeable floor since entry?

**Hybrid** (Pierre's choice): every number is computed deterministically from data we already
have; a thin Opus call only narrates. Data facts from exploration: Tiingo fundamentals are on
the plan (`/fundamentals/<t>/daily` → `marketCap`; `/fundamentals/<t>/statements` → fiscal
period-end `date`s). There is **no free borrow-fee feed**, so borrow is a market-cap + ADV
**proxy** (Grade-C), and next-earnings is a **cadence estimate**, both labeled as such.

**Hard-borrow handling (Pierre's refinement):** a hard-to-borrow short is flagged
`⚠ hard to borrow — short via options (put spread)`, NOT "untradeable" — the short is still
achievable synthetically (consistent with PLAN §11.1 and the fact that primary shorts already
use put-spreads).

## 2. Architecture

```
paper_state.json open ideas ─> elp/risk.py (deterministic facts + thin narration) ─> risk.json
                                                                                       │
   run_paper.sh: track -> catalyst -> risk -> digest -> dashboard   digest soft-derate ┘ + dashboard/email flag
```

## 3. Components

### 3.1 `elp/tiingo.py` — two fail-soft fundamentals helpers
- `fetch_marketcap(ticker: str) -> float | None` — latest `marketCap` from
  `/fundamentals/<ticker>/daily`; `None` on any error/empty.
- `fetch_statement_dates(ticker: str) -> list[str]` — the `date` (fiscal period-end) strings from
  `/fundamentals/<ticker>/statements`; `[]` on any error. (Reuse the existing token/`_fetch`.)

### 3.2 `elp/risk.py` — deterministic core + narration + flag
Config defaults (module constants): `BORROW_MKTCAP_MIN = 2e9`, `BORROW_ADV_MIN = 20e6`,
`EARNINGS_WINDOW = 21`, `CADENCE_DAYS = 91`, `ANNOUNCE_LAG = 40`, `HEDGE_ETF = "SPY"`.

- `borrow_class(ticker, direction, instrument, marketcap, adv) -> "easy"|"hard"|"na"` — `na`
  unless it's a short stock leg (`instrument=="stock" and direction < 0`); `easy` for the broad
  ETF or when `marketcap >= BORROW_MKTCAP_MIN and adv >= BORROW_ADV_MIN`; else `hard`.
- `next_earnings_est(period_end_dates, today) -> (est_date: date|None, days_to: int|None)` — from
  the latest period-end: estimated last announce = period_end + `ANNOUNCE_LAG`; if that is still
  future, it IS the next; else next = period_end + `CADENCE_DAYS` + `ANNOUNCE_LAG`. `(None, None)`
  if no dates.
- `reported_since_entry(period_end_dates, entry, today) -> bool` — did an estimated announce fall
  between `entry` and `today` (edge likely spent)?
- `assess_idea_risk(idea, bars_fn, mktcap_fn, dates_fn, today) -> dict` — orchestrates: supplier
  liquidity (`is_tradeable`) → `ok|thin`; find the short-stock leg (primary or neutralizer) and
  `borrow_class` it (using `mktcap_fn`/`dollar_adv`); `next_earnings_est` + `reported_since_entry`
  on the supplier. Returns
  `{borrow: {ticker, class}, earnings: {days_to, reported_since_entry}, liquidity: "ok"|"thin"}`.
  All fetch fns fail-soft, so missing data → conservative labels (`borrow.class="na"`,
  `earnings.days_to=None`), never a raise.
- `narrate(idea, facts) -> str` — one Opus call (`claude-opus-4-8`) turning the computed facts
  into a one-line risk note; **adds no numbers**. Returns `""` on any error (fail soft).
- `build_risk(state) -> {"generated_utc","model_used","per_idea": {"SUP|CUST": {**facts, "note"}}}`.
- `risk_flag(rv) -> str` — precedence: hard borrow → `⚠ hard to borrow — short via options`;
  reported-since-entry → `⚠ post-earnings (edge likely spent)`; thin → `⚠ thin liquidity`; else `""`.

### 3.3 `risk.py` — entry (mirrors `catalyst.py`/`digest.py`)
Reads `paper_state.json`, runs `build_risk`, writes `risk.json` (generated + gitignored).
Fail-soft: no state / no open ideas / any exception → print + return (exit 0).

## 4. Soft-derate wiring
- `run_paper.sh`: insert `python3 risk.py` after `catalyst.py`, before `digest.py`.
- `elp/digest.py`: `_prompt`/`build_digest` gain an optional `risk=None` map (alongside the
  existing `catalyst`); the prompt includes each idea's borrow/earnings/liquidity flags and is
  told to rank hard-borrow / post-earnings / thin ideas LOWER (noting "short via options" for
  hard-borrow). Backward compatible — existing callers unaffected.
- `digest.py` entry loads `risk.json` (fail-soft `{}`) and passes it in.
- `dashboard.py` / `email_report.py`: show `risk_flag()` beside the catalyst flag.

## 5. Error handling / degradation
Every fetch fails soft (`None`/`[]`); missing data yields conservative labels, never a raise.
`narrate` failing drops only the prose. `risk.py` wraps `build_risk` in `except Exception`. The
digest and UI treat an absent/partial `risk.json` as "no risk context". Numbers are code-computed;
the LLM only narrates.

## 6. Testing (offline, stdlib)
- `tests/test_risk.py` (monkeypatch fetch fns + `narrate`'s `complete`): `borrow_class` for
  ETF/large/small/non-short legs; `next_earnings_est` arithmetic (future vs past last-announce);
  `reported_since_entry` true/false; `assess_idea_risk` on a long-stock-pair (short neutralizer)
  and a short-spread idea (borrow `na`), with a dead-fetch degrading to conservative labels;
  `narrate` returns `""` when the LLM raises; `risk_flag` precedence.
- `tests/test_tiingo.py`: `fetch_marketcap` and `fetch_statement_dates` parse canned JSON via a
  monkeypatched fetch and return `None`/`[]` on error.
- `tests/test_digest.py`: prompt carries risk flags when a risk map is supplied.
- `tests/test_dashboard.py` / `tests/test_email_report.py`: `risk_flag` shown when `risk.json` present.

## 7. Cost
One thin Opus narration call per idea (~6/day) — a few cents/day; far cheaper than the catalyst
ensemble. The deterministic core is free. `narrate` is skippable (fail-soft) with no loss of the
flags.

## 8. Out of scope
- Real borrow-fee / short-interest data (no free feed); exact earnings dates (cadence estimate only).
- Any change to engine open/close (soft-derate only); the options-overlay synthetic-short sizing
  (PLAN §11, gated on Phase 5).
- Greeks/theta risk (belongs to the deferred options overlay, not the cash book).
