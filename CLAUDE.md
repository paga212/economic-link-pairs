# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: research complete, result is a null

This repository tested Cohen & Frazzini's customer-supplier lead-lag effect on free modern
data, and **found it absent under a properly powered, point-in-time test**.

```
p = 0.234    (stable across placebo seeds: 0.234, 0.239, 0.258, 0.242, 0.245)
```

A random rewiring of the same links earns a mean Sharpe of **+0.44** against the real wiring's
**+0.63**. The raw strategy shows +28.8% annualized, Sharpe 0.63, 58% hit rate, market beta
−0.09 — which against zero looks like a discovery, and against the honest null is a
77th-percentile draw. That gap is the whole point of the placebo.

This is a **real null, not a lack of power**: injecting the paper's own effect size into the
real returns is detected at `p = 0.033`, in 5 of 5 placebo seeds. The calibration gate passed
first (false-positive rate 4.8% vs nominal 5.0%, 600 trials).

Full result, limitations and the reasoning are in `NOTES.md` (2026-07-10 entry).

**There is nothing live here.** The daily paper-trade engine, the options overlay, the
expression layer, the LLM overlays, the dashboard and the weekly email were all retired on
2026-07-10 once the result came in. No cron runs, nothing is served, nothing is emailed, and
nothing was ever executed or connected to a broker.

### Run
```
python3 -m unittest discover -s tests   # 123 offline tests, no network
python3 xbrl_build.py                    # SEC XBRL sweep 2013q1-2025q4 -> xbrl_links.json
python3 calibrate.py 40 600 100 0        # calibration gate; run BEFORE quoting any p-value
python3 pairtest.py                      # the test battery: screen -> pooled -> L/S -> placebo
python3 linkcheck.py                     # validate a link universe -> rejected_links.json
# historical phase drivers: phase0/1/2a/2a_build/c_backtest/c_coverage.py
```
`xbrl_build.py` downloads ~5GB of SEC quarterly zips one at a time, parsing and deleting each.
It is already run: `xbrl_links.json` is committed and is the reproducible artifact.

### Architecture
- `elp/fsds.py` — SEC Financial Statement Data Sets reader: streams a quarterly zip, yields
  `MajorCustomers`-tagged facts as `{cik, member, filed, value, tag, uom}`
- `elp/edgar.py` — CIK↔ticker map (canonical common share, not a preferred), `CATEGORY`
  blocklist, and `resolve_member()`: the precision-gated XBRL-member-to-ticker resolver
- `xbrl_build.py` — sweeps quarters, picks each supplier's **principal customer** by largest
  disclosed USD revenue per filing, writes the dated link table `xbrl_links.json`
- `elp/pit.py` — `links_asof()`: dated links → `{formation month: [(supplier, customer)]}`.
  A link is live the month after `filed` and lapses `LIFE_MONTHS = 15` later; a newer
  disclosure supersedes an older one, so a supplier holds one customer in any month
- `elp/backtest.py` — the paper's engine: rank suppliers by their principal customer's
  prior-month return, long the top slice, short the bottom, equal weight, hold one month.
  Accepts a static link list or a point-in-time table
- `elp/pairtest.py` — the test battery: `screen()`, `screened_sharpe()`, `placebo()`,
  `placebo_pvalue()`, `market_beta()`, `suppliers_per_month()`
- `calibrate.py` — the gate: the false-positive rate of screen+placebo under a no-effect null
- `elp/signal.py` — lagged vs contemporaneous pair statistics
- `elp/linkcheck.py`, `elp/liquidity.py` — link validation, dollar-ADV gate
- `elp/tiingo.py` — production prices (with retry); `elp/prices.py` — keyless Yahoo prototype
- `elp/links.py`, `elp/cf_links.py` — legacy link universes (a hand-curated fallback set and the
  free Cohen-Frazzini file). Superseded by `xbrl_links.json`; kept for the phase drivers. The LLM
  extraction path (`elp/llm.py`, `phase_b_build.py`, `universe_links.json`) was removed 2026-07-10:
  the XBRL universe is deterministic, so the pipeline has no LLM in it at all

## The two invariants that make the result mean anything

**1. `screen()` is a pure function of `(links, returns)` and runs on the UNION of pairs over
full history, never month by month.** It filters pairs on `lagged_corr > 0` measured on the
same history the backtest then runs on, which alone is data snooping. `placebo()` applies the
*identical* screen to every random rewiring, so the selection bias lands on both sides. This is
why the null Sharpe is +0.44 rather than zero, and why the real Sharpe is compared to that null
and never to zero. If the real and null universes were screened or traded differently, the
p-value would be meaningless.

**2. Never quote a p-value before `calibrate.py` passes.** Decide what "significant" means while
you still have no stake in the outcome.

## Hard-won lessons (do not relearn these)

- **A resolver cannot be validated by unit tests on synthetic fixtures.** Every consequential
  bug here was invisible to a green suite and obvious the moment the shipped code met real SEC
  data. A reviewer explicitly cleared `_canonical` as "verified as sound" while it corrupted 204
  of 8004 CIKs (`DTE`→`DTB`, `GOOGL`→`GOOG`). Run the real code on real data and read the output.
- **Prove every guard test fails when you remove the behaviour it guards.** Three vacuous tests
  shipped in this project and were caught in review: a fixture with no colliding company, a sort
  assertion whose fixture was already sorted, and four point-in-time tests that passed with the
  `pit` argument ignored entirely.
- **"Principal customer" is not "first in the list".** It silently became "alphabetically first"
  twice, at two different layers. It is the customer with the largest disclosed revenue.
- **A swallowed failure is a defect.** A transient price fetch once rendered as "not enough
  overlapping price history", blaming the data for a network error. Every fallback, skip and drop
  must be counted and printed.

## What this project is about

Cohen & Frazzini, "Economic Links and Predictable Returns" (draft 2006-02-23; *Journal of
Finance*, 2008). Details below were verified against the PDF text (`pdftotext`), not recalled.

Core claim: because of limited investor attention, prices do not promptly incorporate news about
economically linked firms, producing cross-firm return predictability. Links are
**customer-supplier**: under SFAS 131 (SFAS 14 before 1997) a firm must disclose any customer
representing **more than 10% of total sales**; in the linked sample the average customer is
**~20%** of the supplier's sales.

The strategy: each month, long suppliers whose principal customer had the best stock return last
month and short those whose customer had the worst; rebalance monthly. Headline result is a
long/short monthly alpha **over 150 basis points (>18%/yr)**. Baseline portfolios are
**equal-weighted**; risk adjustment uses a **4-factor (Carhart)** model. Coastcast / Callaway
(Section I) is the motivating worked example. Universe is CRSP/Compustat U.S. common stocks
(share codes 10, 11); links come from **Compustat segment files**, 1980-2004.

Our replication substitutes SEC XBRL `srt:MajorCustomersAxis` disclosures (2013-2025) for the
Compustat segment files, which are not free. A null on 2013-2025 is consistent with the effect
having been real in 1980-2004 and since arbitraged away; this test cannot separate that from its
never having existed.

## Conventions

Follow the machine-global conventions in `~/.claude/CLAUDE.md`. This project is deliberately
**stdlib-only** — no third-party dependencies, not even pandas or numpy. There is **no LLM in the
link pipeline**: extraction and resolution must stay deterministic and reproducible. Keep it that
way.
