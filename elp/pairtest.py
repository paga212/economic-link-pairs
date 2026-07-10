"""Honest test battery for the Cohen-Frazzini claim, on monthly data.

The claim: a customer's month-M return predicts its supplier's month-(M+1) return.
The trade: rank suppliers by their principal customer's prior-month return, long the top
slice, short the bottom, equal weight, hold one month. That is `elp.backtest`, unchanged.

This module adds only what is needed to decide whether the claim survives on our universe:

- `screen()`   which links are admissible (economics, then a full-history lagged filter)
- `pooled_stats()` per-pair diagnostics averaged across links (context, never a claim)
- `screened_sharpe()` the single statistic the whole battery turns on
- `placebo()`  the null distribution of that statistic under random customer rewiring
- `market_beta()` residual market exposure of the long/short series (a diagnostic)
- `suppliers_per_month()` cross-section width, i.e. the test's statistical power

WHY THE PLACEBO MATTERS. `screen()` filters pairs on `lagged_corr > 0`, measured over the
same history the backtest then runs on. In isolation that is data snooping: keep the links
that worked and of course the survivors worked. The fix is not to drop the screen but to
apply it *identically to the null*. `placebo()` rewires each supplier to a random customer,
runs the same `screen()`, and recomputes the same statistic. The resulting percentile asks
"does the real wiring beat the best-looking subset of a random rewiring?" and prices in the
selection bias on both sides. The percentile is the only number worth quoting; everything
else in this module is context for it.

`screen()` is therefore a pure function of (links, returns) so `placebo()` can reuse it.
Pure stdlib.
"""
from __future__ import annotations

import random
from statistics import mean, pstdev

from elp.backtest import _cust_of, _next, _prev, long_short_returns, performance
from elp.signal import evaluate_pair

# Wholesale distributors. SFAS 131 forces every pharmaceutical manufacturer to name the big
# three drug wholesalers as >10% customers, and electronics makers to name Arrow / TD Synnex.
# The disclosure is real; the economic link is not. A distributor is a pass-through whose
# stock moves on distribution margins, generic deflation and litigation, not on demand for its
# suppliers' products, so it has no customer news to transmit to them. Dropped on economics,
# before any return is looked at, which is why this cannot overfit.
PASS_THROUGH = frozenset({"CAH", "MCK", "COR", "ARW", "SNX"})

MIN_MONTHS = 36          # aligned lagged observations required before a pair is testable


def screen(links, returns, tradeable=None, min_months: int = MIN_MONTHS):
    """(kept_links, [(link, reason), ...]) — admissible links and why the rest were dropped.

    Pure function of its arguments: `placebo()` depends on this to screen a rewired universe
    exactly as it screens the real one. `tradeable`, when given, is the set of tickers passing
    a dollar-ADV gate; the driver passes None (the XBRL universe is disclosure-derived, not
    liquidity-screened).
    """
    kept, dropped = [], []
    for s, c in links:
        if s == c:
            dropped.append(((s, c), "self_link"))
        elif c in PASS_THROUGH:
            dropped.append(((s, c), "pass_through_customer"))
        elif tradeable is not None and not (s in tradeable and c in tradeable):
            dropped.append(((s, c), "illiquid"))
        else:
            res = evaluate_pair(returns.get(c, {}), returns.get(s, {}))
            if res is None or res["n"] < min_months:
                dropped.append(((s, c), "insufficient_history"))
            elif not res["lagged_corr"] > 0:        # NaN-safe: `NaN > 0` is False
                dropped.append(((s, c), "lagged_corr<=0"))
            else:
                kept.append((s, c))
    return kept, dropped


def restrict_pit(pit: dict, kept: list) -> dict:
    """Keep only screened pairs in each month's link list.

    `screen()` runs once on the union of pairs over full history (the load-bearing
    invariant); this restricts the resulting survivors down onto a point-in-time table
    without re-screening month by month. Public because Task 7's driver imports it.
    """
    keep = set(kept)
    return {m: [p for p in pairs if p in keep] for m, pairs in pit.items()}


def _rewire_pit(pit: dict, pair_map: dict) -> dict:
    """Apply a per-PAIR rewiring to every month of a PIT table, dropping any pair with no
    image. Keyed by (supplier, old customer) rather than by supplier alone: a supplier whose
    principal customer changed over time can carry two live pairs across different months of
    the union, and a supplier-keyed mapping would collapse both onto one image, silently
    losing a pair the real table has to trade."""
    return {m: sorted({pair_map[p] for p in pairs if p in pair_map})
            for m, pairs in pit.items()}


def pooled_stats(links, returns) -> dict:
    """Per-pair stats averaged across links. Diagnostic context, never an alpha claim: the
    paper's result is a portfolio spread, not a mean of pairwise correlations."""
    rows = [evaluate_pair(returns.get(c, {}), returns.get(s, {})) for s, c in links]
    rows = [r for r in rows if r]
    if not rows:
        return {"n_pairs": 0}
    return {"n_pairs": len(rows),
            "contemp_corr": mean(r["contemp_corr"] for r in rows),
            "lagged_corr": mean(r["lagged_corr"] for r in rows),
            "up_minus_down": mean(r["up_minus_down"] for r in rows)}


def suppliers_per_month(links, returns, pit=None) -> dict:
    """{month: number of suppliers with both a signal and a return}. This is the
    cross-section the long/short is formed from, i.e. the test's power. A 4-name book cannot
    reject anything, and reading that as 'no edge' rather than 'no power' is the trap.

    Keying asymmetry, deliberate: on the static path (pit=None) the keys are *holding*
    months, derived from supplier returns. On the point-in-time path the keys are the
    table's own *formation* months. Callers only ever consume `.values()`, so this is
    harmless -- but it means the two paths' keys are not directly comparable.
    """
    if pit:
        return {M: sum(1 for s, c in _cust_of(pairs).items()
                       if returns.get(c, {}).get(M) is not None
                       and returns.get(s, {}).get(_next(M)) is not None)
                for M, pairs in pit.items()}
    cust_of = _cust_of(links)
    months: set = set()
    for s in cust_of:
        months |= set(returns.get(s, {}))
    return {H: sum(1 for s, c in cust_of.items()
                   if returns.get(c, {}).get(_prev(H)) is not None
                   and returns.get(s, {}).get(H) is not None)
            for H in sorted(months)}


def market_beta(series: dict, market: dict) -> float:
    """Beta of the monthly long/short series to the market. A rank-formed spread should sit
    near zero; a large value means the long and short slices carry different betas."""
    common = sorted(set(series) & set(market))
    if len(common) < 12:
        return float("nan")
    xs, ys = [market[k] for k in common], [series[k] for k in common]
    mx, my = mean(xs), mean(ys)
    var = sum((x - mx) ** 2 for x in xs)
    if not var:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var


def screened_sharpe(links, returns, cost_bps: float = 0.0, tradeable=None, pit=None):
    """Annualized Sharpe of the long/short built from the *screened* links. None if the screen
    empties the universe or the series is degenerate. The one statistic the battery turns on;
    `placebo()` recomputes exactly this on each rewiring.

    `pit`, when given, is the {formation month: [(supplier, customer)]} table from
    `elp.pit.links_asof`. `links` is still the union of pairs -- `screen()` always runs on
    that union, never month by month (see module docstring) -- and the surviving pairs then
    *filter* the table via `restrict_pit()` rather than re-screening it.
    """
    kept, _ = screen(links, returns, tradeable)
    if len(kept) < 2:                                  # long_short_returns needs a cross-section
        return None
    table = restrict_pit(pit, kept) if pit else kept
    perf = performance(long_short_returns(table, returns, cost_bps=cost_bps))
    if not perf.get("n"):
        return None
    sharpe = perf["sharpe"]
    return None if sharpe != sharpe else sharpe        # drop NaN (zero-vol series)


def placebo(links, returns, n: int = 1000, seed: int = 0, cost_bps: float = 0.0,
            tradeable=None, pit=None) -> list[float]:
    """Sorted null distribution of `screened_sharpe` under random customer rewiring.

    Each draw permutes the customer column across the supplier column, preserving both name
    sets and every name's own return series, and destroying only the *pairing*. The same
    `screen()` then runs on the rewired universe, so the full-history lagged filter's
    selection bias applies to the null exactly as it applies to the real links. When `pit` is
    given, the rewiring is applied to every month of the table (`_rewire_pit`), keyed per
    (supplier, old customer) PAIR rather than per supplier -- a supplier can carry two live
    pairs across different months of the union (its principal customer changed over time), and
    a supplier-keyed rewiring would silently collapse both onto one image. The rewired union
    passed to `screened_sharpe` is exactly `pair_map.values()`, so the screen and the
    restricted table always agree on which pairs exist. Deterministic for a given seed.
    """
    rng = random.Random(seed)
    customers = [c for _, c in links]
    out = []
    for _ in range(n):
        shuffled = customers[:]
        rng.shuffle(shuffled)
        pair_map = {(s, c_old): (s, c_new)
                    for (s, c_old), c_new in zip(links, shuffled) if s != c_new}
        rewired = list(pair_map.values())
        table = _rewire_pit(pit, pair_map) if pit else None
        v = screened_sharpe(rewired, returns, cost_bps, tradeable, table)
        if v is not None:
            out.append(v)
    return sorted(out)


def placebo_pvalue(real: float, null: list[float]) -> float:
    """One-sided p: how often a random rewiring matches or beats the real wiring. Add-one
    corrected, so it can never report an impossible zero."""
    return (sum(1 for v in null if v >= real) + 1) / (len(null) + 1)


def null_summary(null: list[float]) -> dict:
    """Shape of the null distribution, for reporting alongside the p-value."""
    if not null:
        return {"n": 0}
    return {"n": len(null), "mean": mean(null),
            "sd": pstdev(null) if len(null) > 1 else 0.0,
            "p05": null[len(null) * 5 // 100], "p95": null[len(null) * 95 // 100]}
