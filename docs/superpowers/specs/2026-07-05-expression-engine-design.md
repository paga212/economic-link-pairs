# Expression Engine — paired long/short ideas with liquidity-driven expression

**Status:** design approved 2026-07-05 (brainstormed with Pierre). Awaiting spec
review → implementation plan.
**Builds on:** PR #2 (`dashboard-trade-details`: `describe_open` serializer,
digest note-keying fix). Assume that is merged (or rebased in) first.
**Depends conceptually on:** the live dynamic per-trade engine (`elp/trades.py`,
`track.py`) and the options pricer (`elp/options.py`).

## 1. Context and goal

The live paper-trade currently opens **single directional bets** per supplier
(long the stock on a positive customer signal; short via bear-put-spread on a
negative one). Pierre wants each idea to be a genuine **paired long/short**, and
wants the system to **choose how to express each idea by liquidity** — a stock
pair, a stock-vs-hedge, or a leveraged options structure. This spec defines that
"expression engine."

Guiding constraints (unchanged project ethos):
- **Recommendations only** — never trades, never moves money (hot-zone rule).
- **Deterministic core** — every number is Python; no LLM computes P&L.
- **ponytail full / YAGNI** — stdlib only, reuse existing modules, no new deps.
- **Honesty about data** — options ideas are Grade-C until a real options feed
  exists; every idea is stamped with what would be needed to actually trade it.

## 2. The idea model (Approach 3 — hybrid, approved)

An **idea** is the atom, generated event-driven exactly as today: when a
supplier's customer crosses the ±5% signal, that creates a directional *view* on
the supplier. Each idea is built into a self-contained, two-legged structure,
**opened and closed as one unit**:

- **Primary leg** — the bet on supplier S. Expressed as *either*
  - **cash stock** (long S; or short S as a defined-risk bear-put-spread with
    **snapped strikes**), or
  - **an options structure** — a defined-risk debit vertical
    (**bull-call-spread** for a long view, **bear-put-spread** for a short).

  **Deterministic selection rule (no per-idea judgement):** the primary leg is
  expressed via **options iff** S passes the optionability gate (§3) **and** the
  options overlay is enabled (a global config flag, off until the §10 Phase-5
  gate); **otherwise cash.** Options are the *leveraged* expression — the reason
  to prefer them when available is the implicit leverage + hard risk cap (§4).
- **Neutralizing leg** — what makes it "a long and a short," chosen by liquidity:
  - **a counterpart supplier** with the opposite signal, if a liquid one exists
    → a true stock pair (choice 2); else
  - **an ETF hedge** (broad-market first, sector-extensible) → choice 3.

Two independent, liquidity-gated selectors: **express the bet** (cash vs options)
× **neutralize the bet** (paired supplier vs ETF hedge).

## 3. Liquidity thresholds (frozen-but-config knobs)

All from **dollar-ADV** = mean(close × volume) over a trailing window (default 63
trading days). Requires one data-layer change: `elp/tiingo.py::fetch_daily` must
also return volume (Tiingo daily bars include it); today it returns only price.

| Gate | Default | Purpose |
|---|---|---|
| Stock tradeable | price ≥ $5 **and** dollar-ADV ≥ $5M/day | can enter/exit a real position; also auto-drops penny-stock junk links (e.g. MZTI @ $0.07) |
| Pair counterpart | same (price ≥ $5, ADV ≥ $5M) | counterpart must itself be tradeable; else fall to ETF hedge |
| Optionable (Grade-C) | price ≥ $5 **and** dollar-ADV ≥ $25M/day (optionally ∩ a curated whitelist) | proxy for "listed options with usable OI exist" |

**Honest caveat (must be stated on every options idea):** dollar-ADV proxies
*stock* liquidity, not *options* liquidity. A liquid stock can have illiquid
options. The optionability gate is doubly-approximate; a real chain / OI /
bid-ask feed is required before any options idea is tradeable.

## 4. Sizing — risk-budgeted: $10k maximum drawdown per idea

**Neutrality sets the ratio between the two legs; the $10k risk budget sets the
scale.** The absolute size falls out of the risk cap.

- **Leg ratio:** dollar-neutral for a stock pair; **beta-neutral** for an ETF
  hedge (hedge notional = supplier's trailing beta vs the ETF × supplier
  notional; beta from a rolling regression on the price series — stdlib, cheap).
- **Scale, by expression:**
  - **Defined-risk options primary leg → exact $10k hard cap.** Max loss on a
    debit vertical *is* the premium, so buy **$10k of premium-at-risk**. Leverage
    is *implicit in the risk budget* ($10k of premium controls far more
    delta-notional than $10k of stop-risked stock) — **no separate leverage
    knob**.
  - **Cash legs → ~$10k, soft (stop-based).** No contractual max loss, so size
    off the stop: per-leg notional ≈ $10k ÷ stop-distance. The idea's net return
    is measured as (primary P&L + neutralizing P&L) ÷ per-leg notional, so a 5%
    adverse net move on the stop ≈ $10k when the per-leg notional is ~$200k. This
    is *intended* risk, not guaranteed — a gap can blow through the stop.

Consequences to surface in output:
1. Cash notional = risk budget ÷ stop distance — the two are coupled (tighter
   stop → smaller notional).
2. The **hard-capped, leveraged, defined-risk option** is the structurally
   cleaner way to take $10k of risk; **cash carries gap risk** on the same
   budget. The dashboard shows which cap each idea has ("$10k hard" vs
   "~$10k stop-based, gap risk").

## 5. Exits / lifecycle (idea managed as one unit)

Both legs always open and close **together** — never an orphan leg. Exit fires on
whichever comes first, evaluated on the idea's **net combined return** (both legs,
net of costs), reusing the existing exit machinery in `trades.py`:
- **Signal invalidation** — the customer's trailing return reverts through the
  exit threshold (existing hysteresis) → close.
- **Trailing stop** — peak − TRAIL on the *net* idea P&L, ratcheting (the current
  rule, applied to the combined return). The neutralizing leg dampens both upside
  and stop distance — expected.
- **Options expiry** — if the primary leg is an options structure, close by
  ~15–30 DTE (per PLAN.md §11.2); never held to expiry.

## 6. Dashboard representation

Each idea renders as a two-legged unit with direction in plain English (resolves
the earlier long/short-ambiguity feedback):
- **Idea line:** e.g. `SHORT SWKS (bearish) · driven by AAPL −7% · net +1.2% · 8d`
- **Primary leg:** instrument + direction + concrete structure — cash entry
  price, or **snapped** option strikes + net debit — with its risk-cap tag.
- **Neutralizing leg:** e.g. `paired long QRVO` or `hedge: long XLK (β-neutral)`.
- **Expression tag:** `stock-pair` / `stock-hedge` / `options(leverage)`.
- Option-leg "long/short" words are sub-labeled under the leg and never collide
  with the idea's net direction (stated once, up top).
- Strikes snapped to a realistic listed grid (~$1 for $100–150 names, wider
  outside) — fixes the `129.06`-is-not-a-real-strike issue; the snap flows into
  the Black-Scholes debit too.

## 7. Data gaps — what's needed to actually trade (stamped on every idea)

- **Options ideas:** Grade-C — optionability proxied from ADV, IV proxied from
  realized vol. **Real chain / OI / bid-ask / IV required before trading.**
- **Cash shorts:** borrow fee/availability is a flat proxy.
- Beta/hedge and stock liquidity are fine on current (Tiingo) data.
- Everything remains **paper, recommendations-only, no execution.**

## 8. Interaction with the bad-links problem (separate thread)

- **Liquidity-junk links** (e.g. MZTI @ $0.07) are killed automatically by the
  §3 liquidity gate — the filter is incidentally a junk-link filter.
- **Entity-resolution errors** (e.g. NRP→ATGL, a *wrong* ticker that may still be
  liquid) are **not** caught here — the signal is garbage, not just illiquid.
  That is a data-correctness workstream owed a **separate** step-by-step
  discussion; out of scope for this spec.

## 9. Code architecture

- **New `elp/express.py`** — the selector + structure builders. Given
  (supplier, side, price/volume series, universe), returns an `idea` =
  {primary_leg, neutralizing_leg, expression, risk_cap, tradeability_flags}.
  Pure, deterministic, testable offline.
- **New `elp/liquidity.py`** (or folded into `express.py` if small) —
  `dollar_adv(series)`, `is_tradeable`, `is_optionable`, `beta(a, b)`.
- **Extend `elp/options.py`** — add `bull_call_spread` (leveraged long) sharing
  the existing Black-Scholes core; add a `snap_strike(px)` helper.
- **Extend `elp/tiingo.py`** — `fetch_daily` returns volume alongside price.
- **Refactor `elp/trades.py`** — lifecycle operates on a two-legged *idea* and
  its net return, rather than a lone position. Keep `simulate`'s signal logic;
  wrap entry so each triggered view is built via `express.build_idea(...)` and
  marked/exited on net P&L.
- **`track.py` / `dashboard.py`** — serialize ideas (both legs + tags) into
  `paper_state.json`; render the two-legged view (§6).

## 10. Build sequencing (cash-first, per approved §11.9 gate)

Even though options are *designed* now, the *build* ships in order so we never
lever an unvalidated edge:
1. **Cash expression engine** — pair vs ETF-hedge selection, liquidity gates,
   risk-budget sizing (stock legs), two-legged lifecycle, dashboard. Fully
   verifiable on current data.
2. **Options overlay** — `bull_call_spread`, optionability gate, options primary
   leg with the $10k premium cap, Grade-C flags. Gated behind PLAN.md §11.9
   (positive net-of-cost cash paper alpha) *and* the data caveats.

## 11. Testing / verification

- **Offline unit tests** (no network; the standard for this repo):
  - `liquidity`: `dollar_adv`, `is_tradeable`, `is_optionable`, `beta` on
    synthetic series (known ADV, known beta).
  - `express`: selector picks pair when a liquid counterpart exists, hedge when
    not, options when optionable+leverage; risk-budget sizing yields $10k max
    loss (exact for options premium; notional = 10k/stop for cash); `snap_strike`
    lands on the listed grid; `bull_call_spread` prices sanely.
  - `trades` (two-legged): net-return marking, combined trailing stop, signal
    exit, both legs close together.
- **Live end-to-end:** `track.py` → `digest.py` → `dashboard.py`; hand-check a
  few ideas' legs/sizes/strikes; confirm numbers come from state, not the model.
- Deterministic: identical results across reruns (same standard as the current
  engine).

## 12. Out of scope

- The NRP-style entity-resolution bad-links fix (separate thread).
- A real options-data feed (flagged as the blocker to trading option ideas).
- Beta-neutral *pairs* (pairs stay dollar-neutral; only ETF hedges are
  beta-neutral) — revisit only if residual beta proves material.
