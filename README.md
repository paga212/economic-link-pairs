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

## Status: Phase 0 (data spine + signal-direction check)

Stdlib-only (no third-party deps). Run:

```
python3 -m unittest discover tests   # offline logic tests
python3 phase0.py                    # live: fetches monthly prices, checks signal
```

`phase0.py` pulls monthly prices (Yahoo, keyless — a prototype source, *not*
production; production is Tiingo per [research/08](research/08-data-procurement.md))
for a hardcoded set of known supplier→customer pairs and measures whether a
customer's month-M return predicts its supplier's month-(M+1) return.

**First finding:** on the built-in Apple/AMAT-supplier pairs (large, heavily
covered names) the same-month link is strong (corr ~+0.5) but the one-month
*lag* is absent — the link is real and efficiently priced. Consistent with the
paper's own result that the effect lives in small, neglected suppliers, not
mega-cap-customer suppliers. The real test needs that neglected universe over a
point-in-time sample (Phase 1, using the free Cohen-Frazzini link dataset).
