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

## Status: live forward paper-trade (dynamic per-trade)

Decision (see `NOTES.md`, `research/10`): rigorous free *historical* proof is infeasible
(C-F links are permno-keyed; no free delisted ticker map), so we prove it **forward** —
a live paper-trade logged out-of-sample and scored net of costs as trades close. The live
system is a **dynamic per-trade engine** (`elp/trades.py`): it enters on the customer
signal, manages each trade with a trailing stop + signal-reversal exit, and expresses the
short leg as a defined-risk **bear-put-spread** (no borrow). `track.py` runs the daily tick
and `dashboard.py` renders the results.

Stdlib-only (no third-party deps). Run:

```
python3 -m unittest discover -s tests   # offline logic tests (26)
python3 track.py                         # daily tick: open/manage trades + score OOS closed → paper_state.json
python3 dashboard.py                     # paper_state.json → site/index.html
python3 phase0.py / phase1.py            # earlier signal-direction check / engine on curated set
python3 phase_c_backtest.py              # directional historical check on resolvable C-F links
```

`track.py` needs a Tiingo token (`TIINGO_API_KEY` or `.tiingo_token`). It writes
`paper_state.json` (dashboard + OOS audit trail) and `paper_start.txt` (the OOS boundary).
`run_paper.sh` chains track → dashboard → serve → commit/push on a weekday-evening cron.
Recommendations only — no execution.

Production prices come from **Tiingo** (`elp/tiingo.py`, per
[research/08](research/08-data-procurement.md)); keyless Yahoo (`elp/prices.py`) survives
only as the `phase0.py` prototype and is survivorship-biased.

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
