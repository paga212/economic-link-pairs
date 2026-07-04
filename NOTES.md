# Session notes / handoff (2026-07-04)

Autonomous build session. Everything below is committed and pushed to `main`.
Full plan in `PLAN.md`; literature/data research in `research/`.

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
- **Tests**: 14 offline unit tests, all pass (`python3 -m unittest discover -s tests`).

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

## DECISION NEEDED FROM YOU (I paused here)
Given rigorous free historical proof isn't achievable:
- **1. Prove it FORWARD** — build the live recommender (B, cautious LLM links) and
  paper-trade out-of-sample for months. No more data spend. The plan's validation phase.
- **2. Pay for CRSP-grade data** for a rigorous historical reproduction (WRDS/institutional;
  Norgate doesn't solve the permno link). Real cost/access barrier.
- **3. Reassess the project.** Evidence so far is discouraging: strong decay prior + null
  free historical check + thin/quality-adverse live links.

My honest lean: **the weight of evidence is not encouraging for this specific strategy at
individual scale.** Cheapest real answer = Option 1 (paper-trade forward, low expectations,
hard kill rule). Rigorous historical certainty = Option 2's paid data. Worth an honest
conversation about whether to continue, pivot, or park it.

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
