# Research notes

Literature and data-source research gathered during planning (2026-07-04), to
supplement the source paper (`../Economic Links and Predictable Returns (Cohen &
Frazzini 2006).pdf`). Collected by four parallel research agents; all citations
were required to be verifiable, with uncertainties flagged explicitly. **Treat
every effect-size number below as pre-2026 vintage and verify against the
primary source before encoding it into a model.**

## Files
- [01-effect-persistence-decay.md](01-effect-persistence-decay.md) — has the anomaly survived since 2008?
- [02-related-link-anomalies.md](02-related-link-anomalies.md) — a menu of other cross-firm link signals we could add.
- [03-data-sources.md](03-data-sources.md) — where to get link data and price data as an individual quant.
- [04-implementation-frictions.md](04-implementation-frictions.md) — transaction costs, borrow, backtesting pitfalls.
- [05-synthesis-claims-map.md](05-synthesis-claims-map.md) — one-line claim per paper, assumption clusters, and a table of direct contradictions.
- [06-gap-analysis.md](06-gap-analysis.md) — open research questions the literature hasn't closed, and what would close them.
- [07-options-expression.md](07-options-expression.md) — deep-research report on expressing the signal via options + whether an options-native cross-firm edge exists.
- [08-data-procurement.md](08-data-procurement.md) — decision-ready data shopping list (price/returns, options/IV, links, borrow) with verified-where-possible costs, phased to buy only what's needed.

## Synthesis — the five things that matter for the build

1. **The edge is real but decayed.** Cohen & Frazzini's >150 bps/month is an
   equal-weighted, 1980–2004, largely small-cap result. Pinchuk (2023) finds the
   effect "smaller and loses significance" post-publication; McLean & Pontiff
   (2016) show anomalies fall ~58% post-publication on average. **Do not use the
   2008 headline as a forward estimate.** We build the system partly to *measure*
   the current, live, net-of-cost alpha — not to assume it.

2. **It lives in the hard-to-trade corner.** The alpha concentrates in small,
   illiquid, hard-to-borrow suppliers. Muravyev et al. (2025) show anomaly
   average returns collapse to roughly zero once real borrow fees are charged,
   with profits concentrated in the exact high-fee names you can't easily short.
   So **borrow cost and liquidity modelling matter as much as signal alpha**, and
   a tradable version probably lives in a more liquid subset with less (but
   maybe still positive) alpha.

3. **Shared-analyst coverage may dominate.** Ali & Hirshleifer (2020) build a
   shared-analyst-coverage momentum factor (~1.68%/month) that *statistically
   subsumes* customer-supplier momentum and several other link anomalies. This is
   the single most important adjacent signal — worth building as a companion, and
   a reason to test each link signal's *marginal* contribution rather than
   assuming they add up.

4. **The link data is a build, not a buy.** No cheap API-first customer-supplier
   dataset exists; Compustat Segments (what the paper used) is WRDS-gated. The
   only individual-accessible path is DIY extraction from **SEC EDGAR full-text
   search** (free, filings back to 2001), parsing prose disclosures and
   entity-resolving customer names to tickers. This messy-text parsing is the
   genuine place LLMs earn their keep in this project.

5. **Timing and point-in-time discipline are everything.** Use the 10-K/10-Q
   *filing date* (not fiscal year-end) to know when a link became public.
   Madsen (2017): the customer-return edge exists *before* the supplier's own
   earnings announcement and dissipates after — so entry timing relative to the
   supplier earnings calendar is a real signal refinement. Prices must be
   survivorship-bias-free with delisting returns (favor EODHD, which sells
   delisted history; Tiingo as runner-up).

## Open question the research could not close
No published study computes customer-supplier momentum *net of realistic
transaction and borrow costs*. That is the central unknown, and our own
backtest with cost/borrow modelling is how we answer it before risking capital.
