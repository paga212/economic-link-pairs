# Implementation Plan (DRAFT — pending approval)

Status: **plan mode**. Nothing here is built yet. This is the proposal to agree
on before writing code. Decisions locked with you on 2026-07-04:

- **Data budget:** modest paid (~$50-150/mo)
- **Universe:** S&P 500 to start
- **Delivery:** email digest **and** dashboard webpage
- **LLM role:** LLM-heavy multi-agent

See `research/README.md` for the literature and data-source basis. The one
uncomfortable, load-bearing finding: **the Cohen-Frazzini effect has decayed
since 2008, lives in hard-to-borrow small caps, and no published study measures
it net of realistic trading + borrow costs.** So this system is built to
*measure* the current, live, net-of-cost edge — not to assume the 2008 headline.
Paper-trade before risking capital.

## 1. What we're building

A daily, cron-driven pipeline that scans the US market for customer-supplier
lead-lag pairs and emails / dashboards a ranked list of long/short pair
recommendations expected to earn positive monthly alpha. **Recommendations
only — the system never places trades or moves money** (hot-zone rule).

## 2. The "LLM-heavy multi-agent" boundary

You chose LLM-heavy. Honored — with one guardrail: **agents own orchestration,
messy-text parsing, reasoning, and the writeups; every numeric step (returns,
signal, ranking, backtest, P&L) calls a deterministic Python/pandas function.**
LLMs decide *what* to compute and interpret the results; code computes the
numbers so they're auditable and identical on reruns. You can move that line
anywhere; this is the default.

## 3. The agent fleet + deterministic core

Deterministic modules (no LLM):
- **Data spine** — prices/returns from EODHD (sells delisted history → survivorship-bias fix) or Tiingo; SQLite point-in-time store.
- **Signal engine** — prior-month principal-customer return → rank suppliers → form long/short pairs; respects filing-date lag; liquidity + borrow screens.
- **Backtest engine** — point-in-time, delisting-aware, transaction-cost + borrow-fee modeling, equal- & value-weighted, 4-factor (Carhart) alpha.
- **Delivery** — email (SMTP/Gmail) + static dashboard regenerated daily.

LLM agents (model in parentheses; see §5):
- **Link Discovery Agent** (Opus 4.8) — parse SEC EDGAR full-text search + 10-K/10-Q filings, extract "major customer" (>10% sales) disclosures, entity-resolve customer name → ticker → point-in-time link table. Runs incrementally on new filings; one-time historical backfill up front.
- **Link Verification Agent** (Haiku 4.5) — QA a sample, flag ambiguous/stale links, confirm customer is a listed US common.
- **News/Catalyst Agent** (Opus 4.8) — for top candidate pairs, confirm a genuine customer information event drove the signal and rule out confounding supplier-specific news already priced in.
- **Risk/Borrow Agent** (Opus 4.8 + tools) — borrow availability / hard-to-borrow, ADV/liquidity, earnings-calendar timing (Madsen 2017: edge exists *before* the supplier's own earnings); derate/drop untradeable shorts.
- **Master / Orchestrator Agent** (Fable 5) — collate everything, rank final pairs by expected alpha net of costs and confidence, write the daily recommendation (rationale, ~1-month horizon, caveats), emit email + dashboard payload.

## 4. Cadence

The signal is monthly-horizon (form monthly, hold ~1 month). Proposed: **monthly
formation + daily monitoring.** Each trading day the pipeline refreshes data and
surfaces (a) new recommended pairs at each monthly rebalance, (b) intra-month
changes (big customer move, changed link, earnings-window timing), and (c) status
of open recommended pairs. Confirm or redirect.

## 5. Model routing (your Fable-5 / Opus preference)

- **Fable 5** (`claude-fable-5`, $10/$50 per 1M tok) — deep synthesis: the daily Master ranking/writeup and periodic backtest-calibration reasoning.
- **Opus 4.8** (`claude-opus-4-8`, $5/$25) — link parsing, news/catalyst, risk judgment.
- **Haiku 4.5** (`claude-haiku-4-5`, $1/$5) — bulk filing scans, simple classification, routine fetches.

**Caveat to verify:** Fable 5 needs 30-day data retention (not available under
zero-retention) and may not be enabled on your API plan — the `/model fable5`
picker failed earlier in this Claude Code session (that's the interactive picker,
separate from API access, but a flag worth heeding). Model IDs will be a config
knob that degrades Fable→Opus automatically if Fable 5 isn't available.

## 6. Phased build (each phase independently verifiable)

- **Phase 0 — Data spine.** Vendor integration; S&P 500 + a small hardcoded link set (a few known supplier→S&P-500-customer pairs); monthly returns. *Verify:* reproduce the correct signal direction on a known historical pair.
- **Phase 1 — Backtest engine.** Point-in-time backtest on the small link set with cost + borrow modeling, EW & VW, 4-factor alpha. *Verify:* stable across reruns; sign/magnitude in the literature's ballpark on the same sample.
- **Phase 2 — Link discovery (LLM).** EDGAR parser + entity resolution → point-in-time link table + QA agent. *Verify:* hand-audit a sample of extracted links against the filings (precision target).
- **Phase 3 — Daily pipeline + agents.** Wire Master + News/Catalyst + Risk/Borrow; model routing; cron. *Verify:* end-to-end run on today's data; manually inspect a couple of pairs.
- **Phase 4 — Delivery.** Email + dashboard. *Verify:* receive the email; load the dashboard.
- **Phase 5 — Paper-trading validation.** Log daily recommendations, track realized out-of-sample P&L for several weeks before trusting. This is how we answer the net-of-cost question the literature couldn't.

## 7. Tech stack (ponytail full / YAGNI)

Python + pandas/numpy; `requests` for EDGAR/EODHD; `anthropic` SDK for agents;
stdlib `smtplib` (or Gmail) for email; SQLite (stdlib) for the point-in-time
link table + recommendation log; static HTML/JS dashboard (Flask only if
interactivity demands it); `cron` for scheduling. No heavy frameworks, no new
deps beyond what each job needs.

## 8. Rough cost

- **Data:** EODHD ~$20-60/mo or Tiingo ~$30/mo (verify current pricing pages) — within budget.
- **LLM:** daily Master (Fable 5) + a handful of Opus catalyst/link calls + incremental Haiku filing scans. Rough order: a few dollars/day, well under any sane cap. *These are estimates to confirm once the token profile is measured.*

## 9. Risks & guardrails

- **Recommendations only** — never trades, transfers, or live sends (hot zone).
- **Decay:** expected live alpha is modest and uncertain; we state a calibrated estimate, not the 2008 headline.
- **Link data is noisy:** QA agent + hand-audit sample; supplier discloses customer (often as "Customer A"), entity resolution is error-prone.
- **Short leg can be uneconomic:** borrow fees/availability modeled explicitly; hard-to-borrow names derated or dropped.
- **Cheap data fidelity:** survivorship bias handled via EODHD delisted history; still lower-fidelity than CRSP — validated in Phase 1.

## 10. Resolved decisions (approved 2026-07-04)

1. **Universe:** customers = S&P 500 (clean, liquid signal source); tradable
   suppliers = any liquid US common that names an S&P 500 firm as a major
   customer. (Trading the suppliers is where the alpha lives; EODHD covers all
   US equities so data cost is unaffected.)
2. **Cadence:** monthly formation + daily monitoring/alerts (§4).
3. **Data vendor:** EODHD primary (delisted history → survivorship-bias fix),
   Tiingo fallback.
