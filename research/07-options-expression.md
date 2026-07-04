# Options expression of the lead-lag signal — deep-research report

Produced 2026-07-04 by the deep-research harness (5 angles, 22 sources fetched,
86 claims extracted, 25 adversarially verified — 24 confirmed / 1 refuted).
**All magnitudes are in-sample historical figures, not live-tradable estimates.**
Sources of mixed quality — flagged inline; paywalled papers verified via
abstract/search, not full tables.

## Bottom line

- **The equity edge is real but decayed** and partly a size artifact — assume a fragile, possibly-zero live signal.
- **Leveraging it through single-name options is unlikely to add risk-adjusted alpha** on its own: published option-signal strategies show large raw returns but ~zero risk-model alpha *before* costs, and theta / IV-crush / skew / wide single-name bid-ask can consume a modest, already-decayed directional edge.
- **Defined-risk vertical (debit) spreads** are the more defensible structure for a fragile signal (blunt theta/vega, cap loss) — at the cost of capped upside.
- **There *is* a genuine options-native edge** (option-implied signals lead the same stock, and IV information transfers across economically linked firms) — **but** most single-name IV-spread/skew predictability is largely a *stock-borrow-fee proxy*, not distinct alpha, concentrated in exactly the small/illiquid names where options aren't listed.
- **Practical design → hybrid:** express the linked-firm view through liquid, optionable large-cap customers where possible; cash otherwise; size small; prefer defined risk. The core tension: the biggest edge lives in the names least accessible via listed options.

## Verified findings

**F1 — The equity signal, in-sample.** *(high)* Cohen & Frazzini (2008, JF 63:1977-2011): quintile long-short customer-momentum ≈ **1.55%/month** abnormal (~18.6%/yr), little factor exposure incl. own-momentum; **3.02%/mo (t=2.70)** in high-inattention (low common mutual-fund ownership) suppliers vs 0.55%/mo (insignificant) in low-inattention names. Pinchuk (2023) replicates **122 bps EW / 106 bps VW** decile spread (t>4 / 2.8). Mechanism corroborated by QREF (2014) earnings-CAR transfer and Hou (2007, RFS) slow industry-information diffusion.

**F2 — Decay + size artifact.** *(high)* Pinchuk (2023): VW long-short **not significantly different from zero out-of-sample and negative over 2005-2018** (post-discovery arbitrage). Restricting to the smallest customer/supplier size ratio cuts the effect 2-4x; a customer-return × relative-size interaction *reverses its sign* — much of the headline is a large-customer/small-supplier size lead-lag, not pure information transfer.

**F3 — Options expression: skeptical prior.** *(high)* Goyal & Saretto (2025, RFS 38(6):1783-1821, "Can Equity Option Returns Be Explained by a Factor Model? IPCA Says Yes"): across **46 long-short option strategies** on published signals, average realized returns **>80 bps/month but average IPCA alpha ≈ zero even before transaction costs**. The apparent option premium is largely factor-explained — so friction can plausibly consume a modest, decayed directional edge.

**F4 — Defined-risk verticals are the defensible structure.** *(medium — mechanics textbook, citation is a broker blog)* A bull call debit spread: max profit = strike width − net debit, max loss = debit. The short call adds positive theta and negative vega that partially offset the long call → more resilient to time decay and IV crush than a single long call, at the cost of capped upside. Appropriate for a fragile signal.

**F5 — A genuine options-native edge (same-stock).** *(high)* Option-implied signals predict the *same* underlying's returns and persist up to ~6 months: Cremers & Weinbaum (2010, JFQA 45:335-367) call−put IV spread ≈ **50 bps/week**; Xing, Zhang & Zhao (2010, JFQA 45:641-662) steepest IV smirk underperforms by **10.9%/yr** risk-adjusted, ≥6-month persistence; An, Ang, Bali & Cakici (2014, JF 69:2279-2337) monthly call/put IV *changes* predict next-month returns ≈ **1%/month** quintile spread; JBF (2021) high risk-neutral-skewness earns positive post-week alpha. Muravyev-Pearson-Pollet (2025, JFE) confirm IV transformations predict stock returns.

**F6 — Cross-firm edge exists, but two caveats.** *(high)* (i) **IV information transfers across linked firms:** Fung & Loveland (2025, J. Futures Markets, DOI 10.1002/fut.70036) — around M&A, target IV changes are positively/significantly related to *industry rivals'* IV changes after controlling for return-information transfer (intra-industry IV spillover). (ii) **But most single-name IV-spread/skew predictability is a stock-borrow-fee proxy:** Muravyev-Pearson-Pollet (2025, JFE) show it drops **≥ two-thirds** once high-borrow-fee stocks are excluded — the signal largely proxies the lending fee via put-call parity, not distinct information.

**F7 — Hybrid design is forced by listing rules.** *(high)* ISE Options 4 initial listing: underlying must be widely-held, actively-traded NMS stock with **≥7M public float, ≥2,000 holders, ≥2.4M shares traded in prior 12 months** (delist at 6.3M / 1,600 / 1.8M). Small illiquid suppliers — where the C-F effect is strongest — routinely fail; S&P 500 customers clear easily. Formalizes options-where-liquid / cash-otherwise, and the core tension: biggest edge in least-optionable names.

## Refuted (0-3, do not rely on)

- *"Predictability persists because the stock borrow fee is itself the limit to arbitrage preventing option information from reaching stock prices."* The supported version is only that IV predictability *proxies* borrow fees (Muravyev-Pearson-Pollet 2025).

## Open questions (research could not close)

1. **No source directly tests expressing the customer-supplier lead-lag *through options*** — the near-zero-alpha caution and IV-leads-stock evidence are applied by analogy; a direct backtest net of theta/skew/single-name bid-ask is missing.
2. **Is there a cross-firm *options-native* customer→supplier signal** (does a customer's skew / IV change / options order flow predict the *supplier*)? Fung-Loveland shows intra-industry M&A spillover, not the customer→supplier options channel specifically.
3. **How much clean (non-borrow-fee) IV predictability survives for the large-cap customers that are optionable?** Two-thirds is borrow-fee proxy concentrated in high-fee small names — potentially little clean signal exactly where options are liquid.
4. **Realistic net-of-cost, post-decay Sharpe of a leveraged defined-risk options pair book** after monthly roll, single-name bid-ask, and vega/theta bleed — unquantified by any source.

## Caveats on the evidence

- All figures are in-sample/historical (equity 1980-2004; options mostly 2010-2014-era) — subject to further post-publication decay.
- Pinchuk (2023) is a single-author, apparently non-peer-reviewed working paper; verify magnitudes against the full PDF.
- F4 mechanics are textbook but cited from a broker blog (SpotGamma).
- Muravyev-Pearson-Pollet (JFE 2025) and Fung-Loveland (JFM 2025) verified via abstract (paywalled full text).
- Risk-neutral-skewness sign is genuinely contested (Conrad-Dittmar-Ghysels 2013 negative; Stilger-Kostakis-Poon 2017 / JBF 2021 positive) — horizon- and construction-dependent.

## Direct implications for our build

1. **Options are an overlay, not a rescue.** Do not assume options add alpha; the base case is that they can *subtract* it via friction. Justify options per-trade, not by default.
2. **Default to defined-risk debit spreads** on the optionable leg; treat naked long premium as the exception (only for high-conviction, catalyst-timed entries per Madsen's pre-earnings window).
3. **Hybrid universe is mandatory, not optional** — most alpha-bearing suppliers aren't optionable. Options mostly live on the large-cap *customer* (signal source), so options expression often means trading the *less* alpha-bearing leg. Flag this explicitly per recommendation.
4. **The options-native cross-firm signal (customer IV/skew → supplier) is an untested research bet** — worth a separate exploratory study, not a Phase-1 dependency, and likely entangled with borrow fees.
5. **Backtest must model options P&L** (theta, vega, skew, bid-ask), not just delta — otherwise the leveraged book's economics are fiction. This is a real addition to the backtest engine scope.
