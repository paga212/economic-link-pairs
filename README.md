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

The source paper PDF is in this repo. Implementation notes and verified data
facts live in [CLAUDE.md](CLAUDE.md). No code yet — this is the starting point.
