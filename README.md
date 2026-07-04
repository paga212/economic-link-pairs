# economic-link-pairs

Replicating and backtesting the customer-supplier trading strategy from Cohen &
Frazzini, "Economic Links and Predictable Returns" (2006 draft; *Journal of
Finance*, 2008).

**The idea:** due to investor limited attention, a supplier's stock is slow to
reflect news about its principal customer. Each month, go long suppliers whose
customer had the best return last month and short those whose customer had the
worst, rebalancing monthly. The paper reports a long/short 4-factor alpha of
over 150 bps/month (>18%/yr) on 1980–2004 CRSP/Compustat data, with customer
links taken from Compustat segment files (SFAS 131: customers >10% of sales).

The source paper PDF is in this repo. The implementation plan is in
[PLAN.md](PLAN.md) and the supporting literature/data research in
[research/](research/). Implementation notes live in [CLAUDE.md](CLAUDE.md).

## Status: live recommender + forward paper-trade

Decision (see `NOTES.md`, `research/10`): rigorous free *historical* proof is infeasible
(C-F links are permno-keyed; no free delisted ticker map), so we prove it **forward** —
a live recommender logged out-of-sample and scored as holding months complete.

Stdlib-only (no third-party deps). Run:

```
python3 -m unittest discover tests   # offline logic tests (15)
python3 recommend.py                 # emit + log this month's long/short recs (Tiingo)
python3 score.py                     # score matured recs vs realized returns
python3 phase0.py / phase1.py        # earlier signal-direction check / engine on curated set
python3 phase_c_backtest.py          # directional historical check on resolvable C-F links
```

`recommend.py` needs a Tiingo token (`TIINGO_API_KEY` or `.tiingo_token`). It logs to
`paper_log.jsonl` (the OOS audit trail). Recommendations only — no execution.

Prices come from keyless Yahoo — a **prototype source, not production** (production
is Tiingo per [research/08](research/08-data-procurement.md)) and survivorship-biased.

- **Phase 0** (`phase0.py`, `elp/signal.py`): on the built-in Apple/AMAT-supplier
  pairs the same-month link is strong (corr ~+0.5) but the one-month *lag* is absent
  — the link is real and efficiently priced on these heavily-covered names.
  Consistent with the paper: the effect lives in small, *neglected* suppliers.
- **Phase 1** (`phase1.py`, `elp/backtest.py`): a data-source-agnostic monthly
  cross-sectional long/short engine (rank suppliers by customer's prior-month return,
  long top / short bottom, hold one month, with a cost hook). Verified by unit tests;
  exercised on a small still-listed curated set. Any number it prints off that set is
  **engine validation, not a valid alpha** (tiny, survivorship-biased, not point-in-time).
- **Ground truth** (`elp/cf_links.py`): parses the free Cohen-Frazzini link file
  (1980-2005; permno-keyed suppliers). Using it for a real backtest needs a
  permno→ticker crosswalk + delisted prices — that's Phase 2 (entity resolution) plus
  a real data feed.
