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

## DECISION NEEDED FROM YOU (I paused here)
How to source live customer-supplier links, given named-only free-EDGAR is too thin:
- **A. Named-only** (current default) — safe, no key, but too thin/biased to be a good recommender.
- **B. + cautious flagged LLM inference** of unnamed customers (recovers high-signal links; injects some noise; needs your Anthropic API key).
- **C. Reassess scope** — prove the effect on a historical backtest first; treat the live free-data recommender as unproven.

My lean: **C then B** — first prove there's any live edge at all (it may be decayed to
zero), and only then invest in the harder live-link extraction with cautious inference.
Building a thin, biased live recommender before knowing the edge exists is premature.

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
