# Customer-Supplier Momentum: Practical Implementation Brief

## Practical findings

**Core anomaly.** Cohen & Frazzini (2008), *Journal of Finance* 63(4) (Wiley: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2008.01379.x; working paper PDF: http://www.econ.yale.edu/~shiller/behfin/2006-04/cohen-frazzini.pdf) identify "principal customer" links via Compustat segment files (SFAS 131 >10%-of-sales disclosure; average concentration ~20%). Headline long-short monthly alpha >150 bps, equal-weighted.

**Turnover.** The signal (prior month's customer return) refreshes monthly, so this is structurally a monthly-refresh, near-full-turnover strategy — closer in character to short-term reversal than to 12-month price momentum. Could not obtain a directly-cited turnover statistic from the original paper (see Uncertainties); this is an architectural inference from the strategy's design.

**Transaction costs / capacity — a gap in the literature.** Novy-Marx & Velikov, "A Taxonomy of Anomalies and Their Trading Costs," *Review of Financial Studies* 29(1), 2016 (SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2535173; NBER w20721) find anomalies with >50%/month turnover mostly fail to generate significant net-of-cost spreads even with mitigation. Frazzini, Israel & Moskowitz, "Trading Costs of Asset Pricing Anomalies" (AQR: https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs-of-Asset-Pricing-Anomalies; SSRN 2294498) show real costs for size/value/momentum/short-term-reversal are far lower than academic estimates, but short-term reversal remains the *most* cost-constrained — and neither paper directly tests customer-supplier momentum. **No published study computes customer-momentum net of realistic transaction costs.** A real and important gap.

**Short selling.** Muravyev, Pearson & Pollet, "Anomalies and Their Short-Sale Costs," *Journal of Finance* (2025, Wiley: https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13501) study 162 anomalies: average gross long-short return 0.14%/month collapses to about -0.01%/month once actual borrow fees are charged; returns concentrated in the small subset of high-fee, hard-to-borrow names, and dropping those names flips the *average* anomaly return positive even before fees. Could not confirm customer-supplier momentum was one of their 162, but the mechanism (small suppliers = harder to borrow) is directly applicable.

**Equal- vs value-weighted.** Pinchuk, "Customer Momentum" (SSRN 4338991; arXiv 2301.11394) replicates: equal-weighted long-short decile ~122 bps/month (t>4) vs value-weighted ~106 bps/month (t=2.8) — smaller under VW as expected, but (per this single working paper) not destroyed. Reports the effect has **smaller magnitude and marginal significance in the post-discovery/post-2005 sample**.

**Publication decay.** McLean & Pontiff (2016), *Journal of Finance* 71(1) (SSRN 2156623): across 97 predictors, returns ~26% lower out-of-sample and ~58% lower post-publication. Published 2008 and now 18 years old — assume the strategy sits well into this decay curve.

**Data quality / point-in-time risk.** Compustat segment files contain measurement error (mismatched SIC codes, inconsistent segment totals) and, vs FactSet Revere, are biased toward smaller-supplier/larger-customer pairs; self-reported customer names (esp. pre-1997) often abbreviated. 10-K filings are due 60–90 days after fiscal year-end (accelerated vs non-accelerated filers) — signal formation must respect the actual filing date, not fiscal year-end, to avoid look-ahead bias.

## Design implications for our build

- **Do** treat this as a high-turnover, small-cap-tilted long-short book, not a slow momentum overlay — cost and borrow-fee modeling matters as much as alpha estimation.
- **Do** source real (or realistic proxy) stock-borrow fee data and screen/derate hard-to-borrow names before assuming the short leg is executable at zero cost; per Muravyev et al., the short leg's economics can flip the whole trade.
- **Do** use the 10-K/10-Q *filing date* (not fiscal year-end) to timestamp when a customer link becomes public, and lag signal formation accordingly — build point-in-time link tables.
- **Do** include delisting returns and use a survivorship-bias-free universe — essential given small-cap suppliers delist/get acquired often.
- **Do** cross-check or hand-audit a sample of derived links; known error rates make this a "verify before trusting" dataset.
- **Consider** value-weighting or capping position sizes in the smallest/most illiquid suppliers — Pinchuk's VW replication retains significance, suggesting a more liquid, tradable subset may preserve much of the alpha.
- **Don't** rely on the original 2008 headline alpha as a forward estimate — discount heavily for both general publication decay and this anomaly's documented post-2005 weakening.
- **Don't** assume the "costs are lower than you think" conclusion transfers here — that covers size/value/momentum/reversal by a large manager, not customer-supplier momentum specifically.

## Uncertainties / gaps
- Could not fetch the full text of the original paper (403s on mirrors) to confirm exact turnover, filing-lag convention, or firm-size breakdowns — relying on abstracts/secondary sources. Turnover characterization is an inference from design, not a cited statistic. (Note: we have since extracted the local PDF text — cross-check there.)
- No verified study directly computes customer-supplier momentum net of realistic transaction + borrow costs combined — the single biggest open question for a live implementation.
- Unconfirmed whether Novy-Marx & Velikov's or Muravyev et al.'s anomaly libraries specifically include customer/supplier momentum; applicability is by analogy.
- Pinchuk's "Customer Momentum" is a working paper — treat VW/decay numbers as less vetted than the JF papers.
