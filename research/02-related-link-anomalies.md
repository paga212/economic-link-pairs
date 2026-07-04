# Menu of Economic-Link Lead-Lag Return Anomalies

Baseline: **Cohen & Frazzini (2008)**, "Economic Links and Predictable Returns," *Journal of Finance* 63(4), 1977–2011 (customer-supplier links via principal-customer disclosures; long-short alpha >150bp/month; ~1-month horizon, decaying by month 2-3). Below are other verified link types that could extend the signal set.

## Link types & signals

**Technology / patent similarity.** Lee, Sun, Wang & Zhang, "Technological Links and Predictable Returns," *Journal of Financial Economics* 132(3), 2019, pp. 76–96 (DOI 10.1016/j.jfineco.2018.11.008). Uses patent-based technological-closeness measures; returns of tech-linked peers predict focal-firm returns, long-short alpha ~117bp/month. Stronger for firms with narrow/specific tech focus, low investor attention, high arbitrage costs. Distinct from industry momentum.

**Shared analyst coverage.** Ali & Hirshleifer, "Shared Analyst Coverage: Unifying Momentum Spillover Effects," *Journal of Financial Economics* 136(3), 2020, pp. 649–675. Connected-firm momentum factor (firms sharing sell-side analysts) alpha ~1.68%/month (t=9.67). Notably, this factor spans/subsumes industry, geographic, customer/supplier, and technology momentum factors in regressions — suggesting shared-analyst-coverage may be a unifying mechanism rather than a fully independent signal. Effect stronger for complex/indirect linkages.

**Competitor / product-market peers (text-based).** Hoberg & Phillips, "Text-Based Industry Momentum," *Journal of Financial and Quantitative Analysis*, 2018. Uses TNIC (Text-based Network Industry Classification, from Hoberg & Phillips 2016, *J. Political Economy*, and 2010, *Review of Financial Studies*). Low-visibility TNIC peers (not sharing SIC code) generate large, robust momentum profits, stronger than same-SIC peer momentum and stronger than own-firm momentum in places — consistent with inattention to non-obvious competitors.

**Geographic / headquarters proximity.** Parsons, Sabbatucci & Titman, "Geographic Lead-Lag Effects," *Review of Financial Studies* 33(10), 2020, pp. 4721–4770. Co-headquartered firms in *different* sectors show cross-predictability; long-short risk-adjusted returns ~5–6%/year (roughly half the magnitude of industry lead-lag effects). Effect is *not* concentrated in low-attention/high-arbitrage-cost stocks (unlike most other link anomalies) — attributed to analyst coverage being organized by sector, not geography. (Note: an earlier unpublished job-market paper by Quoc Nguyen, "Geographic Momentum," covers similar territory but final publication venue unconfirmed — lower-confidence.)

**Strategic alliances / joint ventures.** Cao, Chordia & Lin, "Alliances and Return Predictability," *Journal of Financial and Quantitative Analysis* 51(5), 2016, pp. 1689–1717. Alliances 1985–2012; long-short on lagged alliance-partner returns yields ~89bp/month, robust to FF3 + momentum controls. Horizon: ~2 months. Attributed to investor inattention and limits to arbitrage; correlation increases post-alliance partly via elevated M&A probability among partners.

**Common institutional ownership.**
- Gao, Moulton & Ng, "Institutional Ownership and Return Predictability Across Economically Unrelated Stocks," *Journal of Financial Intermediation* 31, 2017, pp. 45–63. Weekly lead-lag predictability (~19bp/week long-short) among stocks with *no* customer-supplier or industry link, but sharing institutional owners — driven by correlated institutional trading, not fundamentals.
- Ying, "Gradual Information Diffusion Across Commonly Owned Firms," *Journal of Financial Economics* 156, 2024. Common-institutional-ownership (CIO) peer-momentum strategy outperforms shared-analyst-coverage momentum in some tests; effect concentrated in low-turnover/passive holders. Suggests a genuinely distinct (ownership-network) mechanism.

**Customer-supplier extensions (same family as Cohen-Frazzini).** Customer-momentum / single-customer-concentration variants are discussed in follow-on literature (e.g., a 2023 arXiv working paper "Customer Momentum," reporting ~122bp/month) — could **not** verify peer-reviewed status; treat as unverified working paper.

## Sources
1. Cohen, L., Frazzini, A. (2008). "Economic Links and Predictable Returns." *Journal of Finance*, 63(4), 1977–2011.
2. Lee, C.M.C., Sun, S.T., Wang, R., Zhang, R. (2019). "Technological Links and Predictable Returns." *Journal of Financial Economics*, 132(3), 76–96. DOI: 10.1016/j.jfineco.2018.11.008.
3. Ali, U., Hirshleifer, D. (2020). "Shared Analyst Coverage: Unifying Momentum Spillover Effects." *Journal of Financial Economics*, 136(3), 649–675.
4. Hoberg, G., Phillips, G. (2018). "Text-Based Industry Momentum." *Journal of Financial and Quantitative Analysis*; TNIC methodology from *Review of Financial Studies* (2010) and *Journal of Political Economy* (2016).
5. Parsons, C.A., Sabbatucci, R., Titman, S. (2020). "Geographic Lead-Lag Effects." *Review of Financial Studies*, 33(10), 4721–4770.
6. Cao, J., Chordia, T., Lin, C. (2016). "Alliances and Return Predictability." *Journal of Financial and Quantitative Analysis*, 51(5), 1689–1717.
7. Gao, G.P., Moulton, P.C., Ng, D.T. (2017). "Institutional Ownership and Return Predictability Across Economically Unrelated Stocks." *Journal of Financial Intermediation*, 31, 45–63.
8. Ying, J. (2024). "Gradual Information Diffusion Across Commonly Owned Firms." *Journal of Financial Economics*, 156.

## Uncertainties / gaps
- All alpha figures are as reported in abstracts/secondary summaries, not independently re-derived — verify exact numbers and sample periods against the PDFs before use.
- Nguyen's "Geographic Momentum" job-market paper: final publication status/venue unconfirmed.
- The 2023 arXiv "Customer Momentum" paper (122bp/month): unverified as peer-reviewed; exclude from any "verified anomaly" list until confirmed.
- Ali & Hirshleifer's spanning result (shared-analyst-coverage subsuming several other link factors) implies real overlap/multicollinearity — a multi-signal model should test *marginal* contribution, not assume additivity.
- Knowledge cutoff Jan 2026; did not check for 2025–2026 replication/critique papers — treat all effect sizes as pre-2026 vintage.
- No distinct, well-cited paper isolating "single large-customer concentration" as its own tradable anomaly separate from Cohen-Frazzini-style customer momentum was found.
