# Implementation Plan (APPROVED — partially built)

Status (as of 2026-07-05): decisions **approved 2026-07-04** and the build is
underway. **Built:** Phase 0 (data spine + signal check), Phase 1 (backtest
engine), Phase 2a (EDGAR extractor), Phase D (dynamic per-trade engine, now the
live system), Phase B (LLM-diversified link universe), most of Phase 3 (Fable-5
Master digest, expression engine, link validation, News/Catalyst agent), and
Phase 4 (delivery: dashboard + basement-independent weekly email) — the forward
paper-trade is running (`track.py`). **Remaining:** Phase 3's Risk/Borrow agent,
Phase 5 (paper-validation window, running), Phase 6/7 (options overlay, gated
behind Phase 5). Per-phase status is marked in §6. The design below —
including the §11 options overlay — remains the plan of record.

Decisions locked with you on 2026-07-04:

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

- **Phase 0 — Data spine.** ✅ **Built** (`phase0.py`, `elp/signal.py`, `elp/prices.py`, `elp/tiingo.py`). Vendor integration; small curated link set; returns. *Verified:* signal direction on known pairs — same-month link strong, one-month lag absent (effect lives in neglected suppliers, as the paper says).
- **Phase 1 — Backtest engine.** ✅ **Built** (`elp/backtest.py`, `elp/cf_links.py`, `phase1.py`). Data-source-agnostic monthly long/short engine + free C-F link parser. *Verified:* stable across reruns; unit-tested.
- **Phase 2 — Link discovery (LLM).** 🟨 **Partial** — Phase 2a EDGAR extractor built (`elp/edgar.py`); Phase B LLM link expansion built and live (`elp/llm.py`, `universe_links.json`). Remaining: entity-resolution hardening + dedicated QA agent. Named-link yield/quality limits documented in `research/09`.
- **Phase D — Dynamic per-trade engine.** ✅ **Built** (`elp/trades.py`, `elp/options.py`, `track.py`) — *the live system.* Signal-triggered trades, trailing stop + signal exit, bear-put-spread shorts, net-of-cost scoring.
- **Phase 3 — Daily pipeline + agents.** 🟨 **Partial** — shipped: the **Master/Orchestrator digest** (`elp/digest.py`, `digest.py`, Fable-5 with Opus-4.8 fallback; ranks/narrates the open book, numbers pulled from state), the **expression engine** (`elp/express.py`: paired two-legged long/short ideas, liquidity-chosen expression), **link validation** (`elp/linkcheck.py`), and the **News/Catalyst agent** (`elp/news.py`, `elp/catalyst.py`, `catalyst.py`: a 3-source RSS + Tiingo + web-search Opus ensemble reconciled by a master, soft-derating `none`/confounded ideas in the digest; fail-soft, recommendations only). *Verified:* live smoke correctly flagged a confounded name and confirmed a real customer-earnings catalyst. **Remaining: the Risk/Borrow agent** (borrow availability / ADV / earnings-window timing derate).
- **Phase 4 — Delivery.** ✅ **Built** — dashboard (`dashboard.py` → `site/index.html`, served by `serve.sh`) **and** a weekly email report (`email_report.py`, stdlib `smtplib`, self-only recipient) sent **from the cloud** by GitHub Actions (`.github/workflows/weekly-email.yml`, Mondays 08:00 UTC, basement-independent). *Verified:* live send landed in the inbox; dashboard served.
- **Phase 5 — Paper-trading validation.** 🟨 **Running** — OOS clock started (`paper_start.txt`); accruing net-of-cost P&L. This is how we answer the net-of-cost question the literature couldn't.

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

## 11. Options expression & execution

*(Deep-planning pass on Fable 5, 2026-07-04, folding `research/07-options-expression.md` into the architecture. Cash-first; options are a gated overlay.)*

Status: **overlay, not core**. Research/07's verdict is binding here: leveraging a decayed equity signal through single-name options can *subtract* alpha (theta, IV crush, skew, wide single-name bid-ask; Goyal-Saretto find ~zero risk-model alpha on option-signal strategies even before costs). Options are added only after the cash strategy is validated (§11.8), only per-trade where a gate passes (§11.1), and only as recommendations — never executions (§11.9).

### 11.1 Overlay decision logic (per recommendation, per leg)

Each monthly recommendation is formed as a **cash pair first**. Then, per leg, a deterministic gate decides whether to *also* emit an options expression. Default outcome is **cash**; options must earn their way in.

**Gate A — Listability/liquidity (hard, all must pass):**

| Check | Threshold (config default) |
|---|---|
| Options listed on the leg's underlying | yes (ISE Options 4-style listing implies ≥7M public float, ≥2,000 holders, ≥2.4M shares traded prior 12 months — names near the 6.3M/1,600/1.8M delisting floor are treated as unlisted) |
| Open interest, candidate strikes | ≥ floor (default 500 contracts across the two legs; config knob) |
| Quoted bid-ask on the vertical | ≤ max fraction of mid debit (default 10%; config knob) |
| Quotes present/fresh on both legs | yes |

**Gate B — Conviction (hard):** leg is in the Master Agent's top conviction tier (top-decile signal, catalyst confirmed by News/Catalyst Agent, no confounding supplier-specific news).

**Gate C — Catalyst timing (hard, per Madsen 2017):** the supplier's next earnings date falls **inside** the intended hold window. The edge concentrates before the supplier's own earnings and dissipates after; long premium with no catalyst in-window is paying theta for drift that may not arrive. If the supplier just reported, the leg stays cash.

**Structure selection when all gates pass:**

| Situation | Structure | Notes |
|---|---|---|
| Default (long or short leg) | **Defined-risk debit vertical** (bull call spread / bear put spread) | Short wing blunts theta/vega and IV crush; max loss = debit. The default, full stop. |
| Exceptional: top conviction + catalyst inside window + cheap IV (IV percentile below config floor vs own 1y history) | Naked long call/put | Emitted only with an explicit `EXCEPTION: undefined-theta` flag and separate risk budget (§11.4). Never the default. |
| Short leg where stock is hard-to-borrow **and** options liquid | Synthetic short / risk-reversal (short call + long put) — **flag-only alternative** | Put-call parity re-embeds the borrow fee in rich puts (Muravyev-Pearson-Pollet), so this is not a free bypass; short call adds early-assignment risk near ex-div. Recommendation states the embedded carry. Default for a hard-to-borrow short remains: derate or drop. |
| Any gate fails | **Cash** (or drop) | Stated in the recommendation with the failing gate named. |

No short premium is ever recommended except as the defined-risk wing of a vertical or the call side of a flagged synthetic.

### 11.2 Structure/contract mechanics (deterministic, rules-based)

All of this is a pure Python function of (spot, chain snapshot, signal date, earnings calendar) — no LLM in the loop.

- **Expiry:** first standard monthly expiry with ≥ 45 calendar days to expiry at formation (config: 45–60 DTE band). The ~1-month hold then exits with ~15–30 DTE remaining — avoids terminal theta acceleration, gamma/pin risk, and holding to expiry.
- **Long strike:** nearest listed strike to spot (ATM).
- **Short strike / width:** nearest listed strike to spot × (1 ± expected move), where expected move = trailing 21-day realized vol scaled to the hold horizon (config multiplier, default 1.0). Deterministic tie-break: rounder/higher-OI strike.
- **Debit sanity:** reject the structure if net debit > 50% of width (config knob) — past that point the risk/reward of the vertical no longer beats cash. Falls back to cash with reason logged.
- **Exit rules (evaluated by the daily monitor, in priority order):** (1) signal invalidation or monthly rebalance → recommend close; (2) supplier earnings reached → recommend close **by T-1 before the supplier's earnings print** unless the exception flag was set (Madsen: edge dissipates after; post-print you hold IV-crushed time value with no thesis); (3) spread value ≥ 75% of max value (config) → recommend early profit-take.
- **Rolls:** there is no rolling as a concept. Each monthly formation is close-old / open-new; if the same pair re-selects, that is two tickets and the backtest charges the spread twice. Keeps the engine and the economics honest.

### 11.3 The hybrid-universe reality (say it out loud, per recommendation)

The structural tension from research/07: **the options usually live on the large-cap S&P 500 customer (the signal source); the alpha-bearing supplier is often small and not optionable.** Trading the customer's options is trading the *less-alpha* leg — the customer's move is the *input*, largely already realized when we form the signal.

Handling, per recommendation:

- The options gate is evaluated **on the supplier leg only** by default. If the supplier is optionable and passes §11.1, an options expression of the supplier leg is emitted alongside cash.
- If only the customer is optionable, the recommendation **stays cash** — we do not synthesize a customer-side options position and call it an expression of the pair. (Customer-side options enter only via the separate research track, §11.6.)
- Every recommendation carries an explicit `expression:` field — `cash`, `cash+options(supplier)`, or `cash-only (supplier not optionable — alpha leg unlisted)` — so the human always sees which leg the leverage would actually sit on and why most pairs will be cash. Expect the majority of pairs to be cash; that is the design working, not failing.

### 11.4 Risk layer

The book previously carried delta and borrow. With the overlay it carries greeks; the Risk agent and daily monitor expand accordingly.

| Exposure | Rule |
|---|---|
| Net premium at risk (all debit structures) | Hard cap as % of notional book (config; sized so a total loss of all open debits costs less than one month of the cash book's risk budget). Per-position debit ≤ per-name cap. |
| Undefined-theta exceptions (naked long premium) | Separate, smaller sub-budget; count-capped (config, default ≤ 2 open at a time). |
| Net theta | Reported daily as **theta burn ÷ calibrated expected monthly alpha**. If that ratio exceeds a config threshold across the book, the monitor flags "theta exceeds edge" and new options recommendations pause. This is the single most honest number in the overlay: the live edge is possibly near zero, and theta is certain. |
| Net vega | Reported; verticals keep it small by construction. Flag if any single name dominates. |
| Net delta | The options book's aggregate delta must stay consistent with the cash signal's intended direction/size — options add leverage per name, not a different book. |
| Gamma / pin | Avoided structurally by the ≥15 DTE exit rule. |
| Assignment (short wings, synthetics) | Daily check: any short call ITM with ex-div inside 5 business days, or short leg deep ITM → early-assignment warning in the digest, with the resulting stock position spelled out (this system only warns; the human holds the position). |
| Sizing philosophy | Size for a **fragile, possibly-zero edge**: the option allocation replaces part of the cash position's risk, never stacks on top of it. Leverage changes the payoff shape, not the risk budget. |

### 11.5 Backtest engine scope expansion

The backtester must reprice the option structures, not just lever delta — otherwise the overlay's economics are fiction. Minimal-but-honest design (ponytail full: Black-Scholes + pandas, no new heavy deps):

- **Pricer:** Black-Scholes with discrete-dividend adjustment; a single small pure function. American early-exercise premium ignored and disclosed (defensible for near-ATM verticals exited pre-expiry; noted as a known approximation).
- **Daily repricing** of each open structure off an IV input, with P&L attribution split delta / theta / vega (finite-difference off the same pricer) so theta bleed is visible in backtest output.
- **IV sourcing, graded:**
  - **Grade A** — actual historical EOD option quotes (EODHD sells a US options add-on; coverage, history depth, and price must be verified before relying on it — unconfirmed). Real bid-ask, real per-strike IV, real skew.
  - **Grade B** — vendor ATM IV only: per-strike prices from BS off ATM IV; skew *not* modeled, disclosed.
  - **Grade C** — no options data: IV proxied by trailing 21-day realized vol × a config spread factor, plus a crude earnings-crush rule (IV step-down of a config fraction on the earnings date). No skew, synthetic crush, disclosed loudly.
- **Costs:** per-leg bid-ask charged as a config haircut (% of premium per leg per side; conservative default, sensitivity-tested across a range rather than asserted as one true number) plus per-contract commission. Grade A uses actual quoted spreads instead.
- **Degrade gracefully and say so:** every backtest report is stamped with its IV grade, and any Grade B/C run prints: *"Options P&L is model-priced from proxied IV — skew and true single-name bid-ask are approximated; treat leveraged-book results as an upper bound."* No silent downgrades.
- **Verification:** overlay backtest must be bit-identical across reruns (same standard as the cash engine), and the theta/vega attribution must sum to total option P&L within tolerance.

### 11.6 Options-native cross-firm signal — separate research track (Track R)

**Not a Phase-1..6 dependency.** The question: does the *customer's* option surface (IV spread, skew, ΔIV) predict the *supplier's* next-month return beyond the customer's stock return? No published source tests this channel (research/07 open question 2); Fung-Loveland shows only intra-industry M&A IV spillover.

- **Caveat first:** most single-name IV-spread/skew predictability is a stock-borrow-fee proxy (≥ two-thirds of it, per Muravyev-Pearson-Pollet). One mitigating nuance: our signal would sit on *large-cap, easy-borrow customers*, the segment where the borrow-proxy contamination is smallest — which is also exactly the segment where the *clean* residual signal may be weakest (research/07 open question 3). Genuinely unknown; treat as a coin-flip research bet.
- **Minimal test:** monthly panel on the existing link table. X = customer's month-end call-put IV spread and monthly ΔIV (S&P 500 chains only — cheap, liquid, data actually obtainable); Y = supplier next-month return. Decile sorts plus a regression controlling for the customer's prior-month *stock* return (the incumbent signal) and supplier size. Pass/fail = incremental predictive power beyond the stock-return signal, not standalone significance.
- **Data:** requires historical customer option chains (Grade A/B source from §11.5) — so Track R naturally sequences after the backtest IV plumbing exists.
- **If it fails, it fails** — the result is logged and the overlay is unaffected, since §11.1 never depended on it.

### 11.7 Agent-fleet & model-routing deltas

| Agent | Change | Model |
|---|---|---|
| **Options-Structuring Agent** (new) | Judgment wrapper around the deterministic structure selector: sanity-checks the chain snapshot, earnings/ex-div calendar, flags stale quotes and assignment traps, writes the per-structure rationale + caveats. All strikes/expiries/greeks come from the Python module — the agent never computes a number. | Opus 4.8 |
| **Risk/Borrow Agent** (expanded) | Adds greeks-book review (§11.4 table), theta-vs-edge flag, assignment warnings. | Opus 4.8 |
| **Chain-Screen scans** (new, bulk) | Daily optionability/liquidity screen of supplier universe (listed? OI? spread?) feeding Gate A — mostly deterministic; Haiku only for messy corner cases. | Haiku 4.5 |
| **Master/Orchestrator** (expanded) | Integrates the `expression:` field, ranks cash vs cash+options, owns the go/no-go narrative. Track R synthesis when run. | Fable 5 |
| Deterministic (no LLM) | BS pricer, chain filter, structure selector (§11.2), greeks aggregator, options backtest module. | — |

### 11.8 Phase-plan revision (cash-first is non-negotiable)

Phases 0–5 of §6 are **unchanged and options-free**. The overlay is appended:

- **Phase 6 — Options overlay (build only after Phase 5 shows positive net-of-cost paper alpha).** Chain screen + Gate A/B/C + structure selector + Options-Structuring/Risk agent deltas + backtest options module (§11.5, at whatever IV grade the data budget supports). Recommendations gain the options expression alongside cash, flagged paper-only. *Verify:* deterministic selector reproduces the same structure from the same chain snapshot across reruns; hand-check a handful of emitted verticals against live chains; backtest attribution sums.
- **Phase 7 — Options paper validation.** Track the option expressions' recommended-vs-realized P&L (marked off real EOD quotes) for several weeks alongside the cash book; report the theta-burn-vs-edge ratio realized, not assumed. Only after this does the overlay graduate from "flagged experiment" to a standing part of the digest.
- **Track R (parallel, non-blocking, anytime after Phase 6's IV plumbing exists):** §11.6 study. Its outcome can add a signal input later; nothing in Phases 0–7 waits on it.

Phase-5 gate to even *start* Phase 6 (config, stated here as the default): cash paper book shows positive net-of-cost P&L over the validation window with the signal behaving as designed (right sign, decile monotonicity). If cash fails, there is nothing to lever — the overlay is cancelled, not "tried anyway."

### 11.9 Guardrails (go/no-go, restated as rules)

1. **Overlay, not rescue.** If the cash edge isn't demonstrably there (Phase-5 gate), no options work proceeds. Leverage on a zero edge is negative-sum after theta and spread — this is the base case to disprove, not a formality.
2. **Cash is the default expression.** Options require Gates A+B+C per leg; any failure → cash, reason logged in the recommendation.
3. **Defined risk is the default structure.** Debit verticals only; naked long premium is a flagged, budget-capped exception; no net short premium ever; synthetics only as flagged borrow-constrained alternatives with the embedded carry stated.
4. **Theta-vs-edge kill switch.** When book theta burn exceeds the calibrated expected alpha by the config multiple, new options recommendations pause automatically until the ratio recovers.
5. **Honest output.** Every options P&L figure carries its IV grade; Grade B/C results are labeled model-priced upper bounds. No recommendation ever cites the 2008 headline alpha as the forward estimate.
6. **Hot zone unchanged.** The system emits option-structure *recommendations* (underlying, strikes, expiry, net debit, max loss, exit rules) that a human could enter. It never places, modifies, or cancels any order — options or otherwise — never connects to a broker, and never moves money. Assignment and exercise decisions are the human's; the system only warns.
