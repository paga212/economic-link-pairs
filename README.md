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

## Status: Phase 1 (backtest engine, interim)

Stdlib-only (no third-party deps). Run:

```
python3 -m unittest discover tests   # offline logic tests (9)
python3 phase0.py                    # live: signal-direction check on known pairs
python3 phase1.py                    # live: long/short engine on a curated set
python3 -m elp.cf_links              # summarize the C-F link file (needs data/cf_links.xlsx)
```

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
