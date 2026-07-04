# Data procurement — decision-ready shopping list

Compiled 2026-07-04 from four verification agents (price/returns, options/IV,
customer-supplier links, borrow). **Every price is a 2026-07-04 snapshot; several
are third-party- or search-sourced and flagged to verify at checkout.** Organized
by our cash-first phasing (`PLAN.md` §6, §11.8): buy only what each phase needs.

## TL;DR — recommended stack

| Need | Recommended pick | Cost | When |
|---|---|---|---|
| Price/returns (survivorship-bias-free) | **Tiingo Power** (REST API, `isActive`/`permaTicker` delisting) — spot-check delisted names in Phase 0; upgrade to **Norgate** if it fails | **$30/mo** (Norgate ~$52/mo equiv) | Phase 0 |
| Customer-supplier links (validation) | **Cohen-Frazzini free dataset** (1980-2004) from Frazzini's NYU data library | **$0** | Phase 0-1 |
| Customer-supplier links (live/current) | **DIY SEC EDGAR full-text extraction** (no vendor exists) | **$0 data** (+ modest LLM extraction cost; ~2-4 wk build) | Phase 2 |
| Borrow — current | **IBKR shortable file + iBorrowDesk free API** (needs IBKR account) | **$0** | Phase 3 |
| Borrow — historical (backtest) | **Conservative float/short-interest/utilization proxy** (D'Avolio-anchored); optional iBorrowDesk paid for real 2015+ history | **$0** (opt. ~$8.50/mo) | Phase 1 |
| Options/IV (backtest w/ skew) | **DiscountOptionData $295 one-time** (2005-2026, per-strike + Greeks) or **ORATS Near-EOD $599 one-time** (cleaner license) | **$0 now** | **Phase 6 only** |
| Options/IV (live snapshot) | **Massive/Polygon Options Starter $29/mo** or **EODHD options add-on $30/mo**; ORATS Delayed $99/mo if backtest is ORATS | **$0 now** | **Phase 6 only** |

**Recurring cost to START (Phases 0-5, cash strategy): ~$30/mo** (Tiingo), plus
pay-per-use LLM API (separate). Everything else is free or deferred to Phase 6.
**Deferred one-time at Phase 6:** ~$295-599 (options history) + ~$29-99/mo (live options).

Not a data cost but a setup dependency: **an Interactive Brokers account** is the
practical backbone — free current borrow data, best small-cap short locate, and
where you'd actually trade. Worth opening early.

---

## Per-need detail

### 1. Price / returns
- **Tiingo Power — $30/mo (verified on pricing page).** Conventional REST API for both backtest pull and daily run; delisted/renamed via `isActive` + stable `permaTicker`; 30+ years claimed. **Risk:** delisting/adjustment *quality* is undocumented — Phase 0 must spot-check a sample of known delisted names (bankruptcies, de-SPACs) before trusting it. This is the lazy-but-honest default: cheapest verified API, with a hard verification gate.
- **Norgate Data Platinum — ~$52.50/mo equiv ($630/yr, third-party-sourced price).** The retail survivorship-bias-free *standard*, delisted names included by design (Platinum→1990, Diamond→1950), rigorous adjustment. **Not a REST API** — local DB + `norgatedata` Python package pulled on a cron. The fidelity upgrade if Tiingo's spot-check fails or we want max backtest integrity.
- **EODHD — $19.99/mo + delisted add-on** (verify which tier gates the delisted endpoint; pre-2018 delistings are price-only). Cheapest but the delisted-tier gating is unconfirmed.
- **Note on history depth:** we do **not** need to reproduce C-F's full 1980-2004 window. EDGAR links only exist from 2001, and the live edge is a recent-decades question. Overlap validation against the free C-F dataset (Tiingo reaches ~1996, Norgate Platinum ~1990) is sufficient to sanity-check the logic.

### 2. Customer-supplier links
- **Free win — the actual Cohen-Frazzini link table (1980-2004)** is downloadable from Frazzini's NYU data library (`pages.stern.nyu.edu/~afrazzin/data_library.htm`, `Customer Supplier Links.xlsx`). Use it to build and validate the whole cash pipeline in Phase 0-1 before touching extraction. **$0.**
- **Current data → DIY SEC EDGAR full-text (efts.sec.gov).** Confirmed viable: coverage 2001-present, JSON API, 10 req/s with a User-Agent. XBRL is **not** a shortcut (concentration-risk tags are poorly/inconsistently applied) — free-text extraction + entity resolution is the route. **$0 data**, modest LLM cost, ~2-4 weeks for a solid v1. **No cheap API-first vendor exists** (re-confirmed: Bloomberg SPLC / FactSet Revere are 5-figure institutional).
- **Core risk:** extraction precision and entity resolution. Firms often disclose "Customer A" with no name (unlinkable), and phrasing varies. No published error-rate benchmark for this task — we measure our own precision against the C-F overlap. This is gap #6 in `06-gap-analysis.md` and the biggest integrity risk to a trustworthy backtest.

### 3. Borrow / short data (you have none today)
- **Current (daily run) — free.** IBKR publishes a daily shortable-shares/fee file (`ftp3.interactivebrokers.com/usa.txt`, forum-corroborated, not live-verified); **iBorrowDesk** re-serves IBKR data with a free JSON API (`/api/ticker/{T}`) giving `fee`/`rebate`/`available`. IBKR's official TWS API gives availability but **not** the fee rate — use the file. Coverage = IBKR inventory, which is where you'd borrow anyway.
- **Historical (backtest) — the genuinely hard part.** No cheap market-wide borrow-fee archive exists for an individual (S3/Markit are institutional). Two realistic paths: (a) **iBorrowDesk paid ~$8.50/mo** unlocks IBKR-inventory history back to ~2015 + CSV (verify price/depth before relying); (b) **proxy the fee** from cheaply-available float, short-interest-%-of-float, and utilization, mapped to conservative tiers anchored to published magnitudes (GC ~0.30%/yr; step up to double digits for low-float/high-SI micro-caps), citing D'Avolio (2002, JFE) for the "special >100bps" threshold. **Bias the proxy high** — an over-charged backtest that still works is trustworthy; an under-charged one is the classic small-cap-short trap.
- **Options sidestep:** a defined-risk bear put spread expresses a short with no borrow at all — but only for names with liquid listed options, which excludes most of the illiquid micro-cap tail. Real for the liquid subset, not a universal fix.

### 4. Options / IV — **defer entirely to Phase 6**
Per `PLAN.md` §11.8 the options overlay is built only after the cash strategy validates, and until then the backtester uses Grade C (realized-vol-proxied) IV at $0. So **buy no options data now.** When Phase 6 arrives:
- **Backtest history:** DiscountOptionData.com **$295 one-time** (2005-2026, per-strike bid/ask/vol/OI + Greeks/IV; license terms unpublished — email to confirm personal-research use) or ORATS Near-EOD **$599 one-time** (2007-present, SMV-cleaned, explicit single-user license — the professional-grade pick).
- **Live snapshot:** Massive/Polygon Options Starter **$29/mo** (IV/Greeks from Starter; raw quotes only at $199) or EODHD options add-on **$30/mo**; ORATS Delayed API **$99/mo** if you want the backtest and live feed identically defined.
- **Small-cap caveat:** most vendors are thin on small-cap options because those names often have no listed options at all; HistoricalOptionData openly excludes illiquid small caps. Confirm your specific tickers before buying.

---

## Verify before buying

- **Tiingo** delisted-data *quality* (spot-check known delisted names in Phase 0) and whether solo-capital trading counts as "personal" vs their $50/mo "Internal Commercial Use" tier.
- **Norgate** exact current price (interactive calculator; $630/yr is third-party-sourced).
- **iBorrowDesk** paid tier price (~$8.50/mo) and history depth — first-party-unverified, and it's the linchpin of the cheap-historical-borrow answer.
- **IBKR shortable FTP** host/path (`usa.txt`) — forum-corroborated, not live-verified.
- **Options vendors (Phase 6):** re-confirm prices, small-cap coverage, and that the license permits personal research use (DiscountOptionData / HistoricalOptionData don't publish license terms).
- **General:** all prices are a 2026-07-04 snapshot; this market re-prices often (Polygon→Massive rebrand Oct 2025, Databento repricing Jan 2025). Re-check the live page immediately before purchase.

## Recommended immediate actions (to unblock Phase 0)

1. Open a **Tiingo** account, get an API key (start on the free tier to build, upgrade to Power $30/mo when we need full history/rate limits).
2. Download the free **Cohen-Frazzini link dataset** for pipeline validation.
3. Open an **Interactive Brokers** account (execution + free current borrow data; no rush, but it's the backbone).
4. Everything else (options data, historical borrow subscription) waits for its phase.
