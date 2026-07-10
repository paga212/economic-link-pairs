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

The source paper PDF is in this repo. 

_A good summary of the paper is:  

Companies are connected. If one company depends heavily on another as its main customer, then bad news for the customer should hurt the supplier too. But investors are busy and often miss these links, so the supplier's stock reacts slowly.

The authors call this "limited attention." Because prices are slow to catch up, you can predict them. They tested a strategy: each month, buy suppliers whose big customers just did well, and bet against suppliers whose customers just did badly.

The result: the strategy earned about 1.5 percent a month, roughly 18 percent a year, in their 1981 to 2004 test. I'd treat that as a historical backtest number worth verifying from the paper directly, not a guarantee of future returns. The effect was strongest for stocks that few investors watched closely, which supports their "people aren't paying attention" explanation.

That's the whole paper: investors overlook obvious business connections, and that creates predictable stock moves._


The implementation plan is in [PLAN.md](PLAN.md) and the supporting literature/data research in [research/](research/). 

Implementation notes live in [CLAUDE.md](CLAUDE.md).

## Status: research complete, and the answer is a null

Tested on free modern data (SEC XBRL customer disclosures, 2013-2025) with a point-in-time link
universe and a permutation test calibrated *before* the answer was computed.

```
p = 0.234     real long/short Sharpe +0.63
              null Sharpe from randomly rewiring the same links: mean +0.44
```

The strategy posts +28.8% annualized, Sharpe 0.63, a 58% hit rate and a market beta of -0.09.
Against zero that reads as a discovery. Against a null built by randomly rewiring the same 135
links through the identical screen, it is a 77th-percentile draw. **That gap is the result.**

This is a real null rather than an absence of power: injecting the paper's own effect size into
the real returns is detected at `p = 0.033`, in 5 of 5 placebo seeds. The calibration gate
passed first (false-positive rate 4.8% against a nominal 5.0%, on 600 trials).

An earlier attempt on a 3-supplier universe returned `p = 0.828`, which was uninformative: no
evidence, and no ability to find any. Expanding to a median of 40 suppliers per formation month
is what made the null meaningful. Caveats that bound the claim (survivorship, era, XBRL tagging
selection) are in `NOTES.md`.

Stdlib-only (no third-party deps, no LLM in the pipeline). Run:

```
python3 -m unittest discover -s tests   # 123 offline logic tests, no network
python3 xbrl_build.py                    # SEC XBRL sweep 2013-2025 -> xbrl_links.json (committed)
python3 calibrate.py 40 600 100 0        # calibration gate; run BEFORE quoting a p-value
python3 pairtest.py                      # screen -> pooled stats -> long/short -> placebo
python3 phase0.py / phase1.py            # earlier signal-direction check / engine on curated set
python3 phase_c_backtest.py              # directional historical check on resolvable C-F links
```

`pairtest.py` and `xbrl_build.py` need a Tiingo token (`TIINGO_API_KEY` or `.tiingo_token`) plus
SEC's free bulk data.

**Nothing runs on a schedule.** The daily paper-trade engine, the options overlay, the LLM
narration layer, the dashboard and the weekly email were retired on 2026-07-10 once the result
came in. No cron, no server, no email. Nothing was ever executed or connected to a broker.

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
