# Gap analysis: open questions in the customer-supplier / link literature

Based on the papers in `01`–`05`. These are the main questions the collected
literature does **not** fully answer. Attributions and "closest paper" are my
reading; underlying claims are as-reported (see `05-synthesis-claims-map.md`).
Several of these gaps are exactly what our own backtest + paper-trading phases
are positioned to partially close — noted at the bottom.

| # | Open research question | Why it's still open | Closest to answering it | Methodology needed to close it |
|---|---|---|---|---|
| 1 | **What is the customer-supplier alpha *net of realistic transaction + borrow costs*?** | The anomaly papers report gross / factor-adjusted alphas; the cost papers study broad anomaly *libraries*, not this effect specifically. No one has joined the two for customer-supplier momentum. | **Muravyev et al. (2025)** (actual borrow fees) and **Novy-Marx & Velikov (2016)** (turnover-based costs) — both by analogy only; unconfirmed the effect is in their samples. | Replicate C&F on a survivorship-bias-free, point-in-time link set; charge *actual* securities-lending fees + effective spreads; report net long-short in a liquid subset vs the full universe; validate with paper/live execution. |
| 2 | **What is the live alpha of the exact C&F construction in the current decade?** | Compustat segment data is WRDS-gated; recent replications are thin and mostly preprints. Pinchuk gives a pre/post-discovery *split*, not a rolling recent-years estimate. | **Pinchuk (2023)** | Rolling-window replication through ~2025 on point-in-time segment / EDGAR links; report alpha by sub-period with confidence bands and a decay trend. |
| 3 | **Does a tradable, cost-aware customer-supplier strategy retain alpha *after controlling for shared-analyst-coverage momentum*?** | Ali & Hirshleifer show subsumption in *gross, paper-portfolio* spanning regressions; nobody re-ran the test on *net-of-cost* returns or as a tradable incremental-IR question. | **Ali & Hirshleifer (2020)** | Build both factors on one sample; run spanning regressions on net-of-cost returns; test incremental information ratio, not just gross alpha significance. |
| 4 | **How much of the effect is a genuine economic-link channel vs a repackaged small-follows-large / intra-industry lead-lag?** | Correlated exposures (size, liquidity, industry lead-lag) are hard to disentangle; Pinchuk flags it as "partly driven" but doesn't cleanly decompose it. | **Pinchuk (2023)**; **Hou (2007)** | Double-sort / orthogonalize the customer-supplier signal against a size lead-lag factor and Hou's intra-industry lead-lag; test residual alpha. |
| 5 | **What is the optimal entry/exit timing relative to the attention (earnings) window?** | Madsen establishes the *mechanism* (edge exists before the supplier's own earnings, dissipates after) but stops short of designing and testing a trading rule. | **Madsen (2017)** | Event-time backtest conditioning entry/exit on days-to-supplier-earnings; compare net alpha across timing rules to find the best-executing window. |
| 6 | **Do DIY EDGAR/NLP-extracted links reproduce the academic result, or does extraction noise destroy it?** | Purely an implementation/data-engineering question — academics use clean Compustat segment data, so no one has published the comparison. | *None directly* — flagged only in our data-sources brief (`03`). | Build the EDGAR link set; benchmark precision/recall against a Compustat sample where obtainable; compare backtest alphas from each link source to bound the noise penalty. |
| 7 | **What is the strategy's capacity (breakeven AUM before market impact erases the edge)?** | Capacity work (e.g. Frazzini-Israel-Moskowitz) targets large-cap factors; the customer-supplier effect lives in small, illiquid suppliers, where capacity is likely low but unquantified. | **Frazzini, Israel & Moskowitz** (framework); **Novy-Marx & Velikov (2016)** (turnover) | Combine ADV / position-size constraints with a market-impact model; solve for the AUM at which net alpha crosses zero. |

## What our project can partially close

The build in `../PLAN.md` directly produces evidence on several of these:
gaps **1, 2, 5, 6** are outputs of the backtest + paper-trading phases (net-of-cost
alpha on our own link set, a current-decade estimate, timing-rule comparison,
and the EDGAR-vs-clean-data fidelity check). Gap **3** we can approach if we also
build the shared-analyst-coverage companion signal (research brief `02`). Gaps
**4** and **7** need dedicated econometric / market-impact work beyond the daily
recommender and are out of scope for the first build.
