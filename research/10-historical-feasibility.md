# Historical-proof feasibility (Phase C, 2026-07-04)

Goal: prove the customer-supplier lead-lag effect on a historical backtest before
investing in live link extraction (user chose "C then B").

## The wall: rigorous free historical proof is not feasible

Two compounding free-data limits:
1. **The C-F link file is CRSP-permno-keyed** (suppliers have no ticker/name). We
   harvested a free permno→name map from the file's own customer columns, but only
   ~4,848 supplier permnos are nameable that way, and most are then unresolvable.
2. **No free historical/delisted ticker map.** The SEC `company_tickers.json` lists
   only *currently-listed* firms, so C-F-era firms that later delisted don't resolve.

Net: of **26,339 C-F link rows, only 28 distinct supplier→customer pairs (23 suppliers)
resolve to current tickers** — all survivors, all still listed today. That is far too
thin and survivorship-biased to be a rigorous reproduction.

## Directional check on the 23 resolvable links (not proof)

`phase_c_backtest.py`, link era 1998-2008 (131 months), Tiingo prices, static links:

| | ann return | ann vol | Sharpe | hit |
|---|---|---|---|---|
| gross | -2.5% | 34% | -0.07 | 52% |
| net (10bps) | -4.9% | 34% | -0.14 | 50% |

**No positive effect** in the free-testable sample. This is *consistent with* the
documented decay (research/01) but is **not conclusive** — 23 survivor links, static,
raw tickers is a weak test that could miss a real effect or reflect the biased sample.

## Where this leaves the project (decision needed)

Rigorous historical proof would need **CRSP-grade data** (permno→historical ticker +
delisting returns) — WRDS/institutional, effectively gated for an individual. Norgate
(~$52/mo) has survivorship-free *prices* but not the permno→ticker *link*, so it does
not fully unblock this either.

Options:
- **1. Prove it FORWARD instead.** Skip to B (live recommender with cautious LLM links),
  paper-trade out-of-sample for several months. Accepts we can't prove the past; tests
  the future. No further data spend. (This is the plan's validation phase anyway.)
- **2. Pay/obtain CRSP-grade data** for a rigorous historical reproduction. Real cost /
  access barrier; may need a university affiliation.
- **3. Reassess the project.** The accumulated evidence is discouraging: strong decay
  prior + this null directional check + thin, quality-adverse live links. Honestly weigh
  whether an individual-accessible customer-supplier strategy clears the bar, or pivot.

**Honest recommendation:** the weight of evidence (decay literature + null free
historical check + thin/biased live links) is not encouraging for *this specific*
strategy at individual scale. The cheapest way to get a real answer without more data
spend is **Option 1 — build the live recommender and paper-trade it forward** as a
genuine out-of-sample test, going in with low expectations and a hard "kill if it
doesn't clear the bar" rule. If the user wants rigorous historical certainty first,
that requires Option 2's paid/institutional data.
