# Session notes / handoff (2026-07-04)

Autonomous build session. Everything below is committed and pushed to `main`.
Full plan in `PLAN.md`; literature/data research in `research/`.

> **Update 2026-07-05 (correction to the record below).**
> - **Phase B shipped.** The LLM-diversified link universe is built and live (commits
>   `3ac4afa`, `95575c0`, `9b37f19`); the forward clock was restarted on it. Items in
>   "To make it a real forward test" that hinged on the Anthropic key for Phase B are done.
> - **The monthly `recommend.py`/`score.py` flow was superseded** by the daily dynamic
>   tracker `track.py` (→ `paper_state.json`). Those two files no longer exist; ignore the
>   monthly-cron snippet below and use `run_paper.sh` (already on a weekday-evening cron).
> - **Test count is now 26** (not 14); run `python3 -m unittest discover -s tests`.

## Built and verified this session
- **Phase 0** (`phase0.py`, `elp/signal.py`, `elp/prices.py`): stdlib data spine +
  signal-direction check. Finding: on heavily-covered Apple/AMAT suppliers the same-month
  link is strong (~+0.5) but the one-month lag is absent — effect lives in *neglected*
  suppliers, as the paper says.
- **Phase 1** (`elp/backtest.py`, `elp/cf_links.py`, `phase1.py`): data-source-agnostic
  monthly long/short engine (verified by unit tests) + parser for the free Cohen-Frazzini
  link file (26k links, 1980-2005, permno-keyed).
- **Phase 2a** (`elp/edgar.py`, `phase2a*.py`): SEC EDGAR link extractor.
- **Data**: Tiingo wired as production prices (`elp/tiingo.py`), token validated.
- **Tests**: 26 offline unit tests, all pass (`python3 -m unittest discover -s tests`).
  *(Was 14 on 2026-07-04; the suite grew with Phase B/D.)*

## Key empirical findings
1. **Tiingo works but needs `permaTicker`.** Delisted spot-check: CELG retained through
   2019, but raw ticker "MON" returned a *different reused-ticker company* (recycling
   trap), LEHMQ empty. Phase 2 must key on permaTicker, not raw tickers. (`research/08`)
2. **Free-EDGAR named-link yield is ~4% and quality-adverse.** (`research/09`) Modern
   10-Ks usually file concentration as "one customer accounted for >10%" — unnamed,
   often unquantified. The customers that *are* named skew to retailers/distributors
   (Walmart, Target, Synnex = weak lead-lag signal); the high-signal tech links
   (Apple ↔ chip suppliers) are unnamed. So the named-only universe is thin AND biased.

## Phase C attempted (you chose "C then B") — hit a free-data wall
Tried to prove the effect on a historical backtest. Result (`research/10`):
- Rigorous free historical proof is **infeasible**: C-F links are permno-keyed and there
  is no free historical/delisted ticker map, so only **~28 of 26,339 links resolve** to
  current tickers (all survivors).
- Directional check on the 23 resolvable links (1998-2008): long/short **-2.5%/yr gross,
  Sharpe ~0** — no positive effect. Consistent with decay, but too thin/biased to be
  conclusive.

## Decision made: Option 1 — prove it forward (BUILT, dynamic per-trade)
Live daily tracker is running (superseded the earlier monthly recommender):
- **Strategy:** signal-triggered directional trades (customer trailing-21d return ±5%),
  dynamic exits — trailing stop (peak−5%, ratcheting) OR signal reversal (hysteresis),
  no time cap. LONG = cash stock; SHORT = **bear-put-spread** (no borrow, defined risk).
- `elp/trades.py` (engine) + `elp/options.py` (BS spread pricer, Grade-C proxied IV).
- `track.py` — daily: open trades (live stops) + OOS closed trades net of costs →
  `paper_state.json` (+ `paper_start.txt` = OOS boundary, **2026-07-04**).
- `dashboard.py` → `site/index.html`, served always-on at http://100.103.143.120:8787/.
- Cron: `0 22 * * 1-5` (weekday evenings) runs track → dashboard → serve → commit/push.

**Net-of-cost finding (in-sample, hand-set):** gross +0.89%/trade → NET −0.10%
with stock shorts, **+0.39% with bear-put-spread shorts** (kills borrow + caps the short
tail) → −0.11% at 2× costs. The spread number is a **Grade-C optimistic upper bound**
(flat IV, no skew, only 25bps stock-notional cost); real option bid-ask + put skew would
erode it. Needs real options data (Phase 6) to confirm.

### To make it a real forward test (remaining, mostly your calls)
- **~~Run it monthly.~~** *(Superseded 2026-07-05.)* The monthly `recommend.py`/`score.py`
  cron below no longer applies — those files were replaced by the daily dynamic tracker.
  The live cadence is `run_paper.sh` on `0 22 * * 1-5` (weekday evenings): it runs
  `track.py` → `dashboard.py` → `serve.sh`, then commits `paper_state.json` / `paper_start.txt`.
- **Anthropic key** → unlocks Phase B: LLM-inferred links from EDGAR to diversify the
  Apple-heavy universe (drop the key in a file like the Tiingo one).
- **Delivery** → email + dashboard once you give the target (couldn't find `macro-dashboard`).
- **Kill rule** → set your bar (strawman ≥0.5 Sharpe / 5-10 ideas); if paper P&L doesn't
  clear it after N months, stop. Honest prior: the evidence says this is likely weak.

### Known limitation
The `HIGHSIGNAL_LINKS` universe is Apple-supplier-heavy, so the long/short legs are
internally correlated (concentrated bets, not a diversified factor). Phase B LLM link
expansion is what diversifies it.

## Other open inputs (none blocking, all previously raised)
- Fable-5 key test (drop your Anthropic key in a file, same as Tiingo).
- Success bar: net Sharpe + ideas/month (strawman: ≥0.5 Sharpe, 5-10 ideas).
- Is $10-20k **per idea** or **total** book?
- Where does the `macro-dashboard` project / delivery target live? (not found in ~/projects)

## How to run
```
python3 -m unittest discover -s tests   # 14 tests
python3 phase0.py        # signal-direction check (Yahoo)
python3 phase1.py        # long/short engine (Tiingo)
python3 phase2a.py       # EDGAR extraction on known suppliers
python3 phase2a_build.py 30   # named-link yield sample
```
