# Synthesis: claims map, clusters, and contradictions

Cross-paper synthesis of the literature in `01`–`04`, produced during planning
(2026-07-04). **All claims are as reported by the research agents (abstracts /
secondary summaries), not re-derived — verify any number against the source
before relying on it.** Effect sizes are pre-2026 vintage.

## Core claim of each paper (one sentence)

1. **Cohen & Frazzini (2008)** — Stock prices under-react to news about a firm's principal customer, so buying suppliers of winning customers and shorting suppliers of losing ones earns >150 bps/month.
2. **Pinchuk (2023), "Customer Momentum"** — The customer-momentum effect replicates but is smaller and loses significance after the 2008 publication, and is partly a small-follows-large lead-lag.
3. **McLean & Pontiff (2016)** — Documented anomalies fall ~26% out-of-sample and ~58% after publication, concentrated in illiquid, high-idiosyncratic-risk stocks.
4. **Madsen (2017)** — Customer returns predict supplier returns *before* the supplier's own earnings announcement but not after, because scheduled announcements draw attention that resolves the mispricing.
5. **Menzly & Ozbas (2010)** — Returns are cross-predictable along supplier/customer *industry* links, and the effect shrinks as analyst coverage and institutional ownership rise.
6. **Hou (2007)** — Intra-industry information diffuses slowly from big firms to small ones, producing a lead-lag strongest in small, neglected, less-competitive industries.
7. **Cohen & Lou (2012), "Complicated Firms"** — A "pseudo-conglomerate" built from a diversified firm's segment industries predicts the conglomerate's next-month return, because complex firms are harder to process.
8. **Shahrur, Becker & Rosenfeld (2010)** — Customer→supplier return predictability holds across 22 developed markets, not just the US.
9. **Ali & Hirshleifer (2020)** — A single "shared-analyst-coverage" momentum factor (~1.68%/month) statistically *subsumes* customer-supplier, industry, geographic, and technology spillover anomalies.
10. **Lee, Sun, Wang & Zhang (2019)** — Firms linked by patent-based technological similarity show cross-predictable returns (~117 bps/month), distinct from industry momentum.
11. **Hoberg & Phillips (2018)** — Text-based (TNIC) product-market peers, especially low-visibility non-SIC ones, generate large momentum spillover from inattention to non-obvious competitors.
12. **Parsons, Sabbatucci & Titman (2020)** — Co-headquartered firms in *different* sectors cross-predict returns (~5-6%/yr), and — unusually — the effect is *not* concentrated in low-attention stocks.
13. **Cao, Chordia & Lin (2016)** — Lagged returns of a firm's strategic-alliance partners predict its returns (~89 bps/month) over the next ~2 months.
14. **Gao, Moulton & Ng (2017)** — Economically *unrelated* stocks sharing institutional owners show weekly lead-lag (~19 bps/week) driven by correlated institutional trading.
15. **Ying (2024)** — Information diffuses gradually across commonly-owned firms, and a common-ownership momentum strategy can outperform shared-analyst-coverage momentum, concentrated in passive/low-turnover holders.
16. **Novy-Marx & Velikov (2016)** — Anomalies with >50%/month turnover mostly fail to produce significant net-of-cost spreads even with cost-mitigation.
17. **Frazzini, Israel & Moskowitz (working paper)** — Real-world trading costs for size/value/momentum/reversal are far lower than academic estimates, so these strategies are more scalable than believed (reversal least so).
18. **Muravyev, Pearson & Pollet (2025)** — Across 162 anomalies, average long-short returns collapse to ~zero once actual short-borrow fees are charged, with profits concentrated in the few hard-to-borrow names.

## Clusters by shared assumption

- **A — Limited-attention cross-firm lead-lag** (prices under-react to linked-firm news; effect lives in small/neglected/low-coverage names): 1, 2, 4, 5, 6, 7, 8, 10, 11, 13. *(Our strategy's home cluster.)*
- **B — The channel is an information/ownership network, not the economic link itself**: 9, 14, 15.
- **C — Anomaly decay / publication effect**: 3, 2.
- **D — Frictions determine tradability** (turnover, transaction costs, borrow fees): 16, 17, 18.

## Direct contradictions (both positions, papers, and likely cause)

| # | Point of dispute | Position A | Position B | Likely reason they disagree |
|---|---|---|---|---|
| 1 | Are cross-firm link anomalies distinct effects, or one factor? | Each economic link is its own standalone anomaly with independent alpha — **Cohen & Frazzini (2008); Menzly & Ozbas (2010); Lee et al. (2019); Cao et al. (2016); Hoberg & Phillips (2018)** | Shared-analyst-coverage momentum statistically *subsumes* them; they're one analyst-attention factor — **Ali & Hirshleifer (2020)** | **Methodology + era.** A&H (later, 2020) run a *joint spanning regression* against a purpose-built connected-firm factor using broad analyst-network data; the earlier papers each tested one anomaly univariately, without controlling for a common analyst-network factor, so overlap was invisible to them. |
| 2 | Do these effects concentrate in low-attention / high-arbitrage-cost stocks? | Yes — concentrated in small, neglected, low-coverage names — **Cohen & Frazzini (2008); Menzly & Ozbas (2010); Hou (2007); Lee et al. (2019)** | No — geographic lead-lag survives even in well-covered stocks — **Parsons, Sabbatucci & Titman (2020)** | **Link type / transmission channel.** Analyst coverage is organized *by sector*, not geography; cross-sector co-HQ links (Parsons et al.) evade the sector analysts who would otherwise arbitrage them, so the low-attention precondition doesn't bind for that link type. Different pair construction (co-HQ cross-sector) vs economic/industry links. |
| 3 | Do realistic trading & borrow costs destroy anomaly profits? | Largely yes — high turnover and borrow fees erase most net alpha — **Novy-Marx & Velikov (2016); Muravyev, Pearson & Pollet (2025)** | No — real costs are far lower than academics assume; strategies scale — **Frazzini, Israel & Moskowitz** | **Cost source + universe.** FIM use a large manager's *live execution fills* on liquid large-cap size/value/momentum/reversal; NMV use *modeled effective spreads* across the full cross-section; Muravyev use *actual securities-lending fees*. FIM's optimism is a large-cap, tradable-name result; NMV/Muravyev include the small, high-turnover, hard-to-borrow names where costs bite. |
| 4 | Which network is the true diffusion channel? | Shared analyst coverage (subsumes the rest) — **Ali & Hirshleifer (2020)** | Common institutional ownership (can outperform shared-analyst) — **Ying (2024); Gao, Moulton & Ng (2017)** | **Era + network definition.** Ying (2024) uses more recent ownership data in which the post-2015 rise of passive/index funds strengthens the common-ownership channel; different network construction (analyst co-coverage vs 13F common holders) and later test window than A&H (2020). |
| 5 | Is the customer-supplier effect still alive at full strength? | Yes — a robust standalone effect, >150 bps/month — **Cohen & Frazzini (2008)** | No — smaller and statistically insignificant post-discovery — **Pinchuk (2023)**; consistent with general post-publication decay — **McLean & Pontiff (2016)** | **Sample window (temporal), not a methods flaw.** C&F's sample ends 2004, pre-publication; Pinchuk includes the post-2005 out-of-sample period where arbitrage capital eroded the effect — exactly the mechanism McLean & Pontiff document across anomalies. |

**Bottom line for the build:** contradictions 1, 3, and 5 all cut the same way
for us — the live, net-of-cost, marginal-of-other-signals alpha of a
customer-supplier strategy is smaller and more fragile than the 2008 headline.
This is why the plan ends in paper-trading validation rather than assuming the
effect. See [[README]] and `../PLAN.md` §6, §9.
