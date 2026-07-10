"""Monthly cross-sectional long/short backtest engine (data-source-agnostic).

Given customer-supplier links and per-name monthly returns, each month it ranks
suppliers by their principal customer's *prior-month* return, goes long the top
slice and short the bottom slice (equal weight), and holds one month. Pure stdlib,
deterministic (stable tie-break), with a linear transaction-cost hook.

This is the engine only. The *validity* of any result depends entirely on the link
set and price data fed in — a survivorship-biased or non-point-in-time input yields
a non-valid number no matter how correct the engine.
"""
from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev

Returns = dict  # {ticker: {(year, month): monthly_return}}
Links = list    # [(supplier, customer), ...]  (first customer listed = principal)


def _prev(key: tuple[int, int]) -> tuple[int, int]:
    y, m = key
    return (y, m - 1) if m > 1 else (y - 1, 12)


def _next(key: tuple[int, int]) -> tuple[int, int]:
    y, m = key
    return (y, m + 1) if m < 12 else (y + 1, 1)


def _cust_of(pairs: Links) -> dict[str, str]:
    """{supplier: principal customer}. First listed wins, matching the paper's 'principal'."""
    out: dict[str, str] = {}
    for s, c in pairs:
        out.setdefault(s, c)
    return out


def long_short_returns(links, returns: Returns,
                       cost_bps: float = 0.0, side_frac: float = 0.34) -> dict:
    """{(year, month): long-short holding-month return}. Formation = holding month - 1.

    `links` is either a static [(supplier, customer)] list, or a point-in-time
    {formation month: [(supplier, customer)]} mapping (see elp/pit.py) so each month
    ranks only the links disclosed by then.

    cost_bps: round-trip cost per leg in basis points, charged on both legs each month
    (full monthly turnover assumed). side_frac: fraction of names in each of long/short.
    """
    pit = isinstance(links, dict)
    if pit:
        holding_months = {_next(M) for M in links}
    else:
        cust_of = _cust_of(links)
        holding_months = set()
        for s in cust_of:
            holding_months |= set(returns.get(s, {}))

    out: dict = {}
    for H in sorted(holding_months):
        M = _prev(H)
        cust_of_M = _cust_of(links[M]) if pit else cust_of
        sig: dict[str, tuple[float, float]] = {}
        for s, c in cust_of_M.items():
            rc = returns.get(c, {}).get(M)   # customer prior-month return = signal
            rh = returns.get(s, {}).get(H)   # supplier holding-month return
            if rc is not None and rh is not None:
                sig[s] = (rc, rh)
        n = len(sig)
        if n < 2:
            continue
        ranked = sorted(sig, key=lambda s: (sig[s][0], s))  # ascending by customer prior return
        k = max(1, min(round(n * side_frac), n // 2))       # disjoint long/short slices
        shorts, longs = ranked[:k], ranked[-k:]
        ls = (mean(sig[s][1] for s in longs)
              - mean(sig[s][1] for s in shorts)
              - 2.0 * cost_bps / 1e4)
        out[H] = ls
    return out


def signal_ranking(links: Links, returns: Returns, month: tuple[int, int]) -> list:
    """[(supplier, customer, signal)] for a single formation month, sorted desc by signal
    (signal = the supplier's principal customer's return in `month`)."""
    cust_of = _cust_of(links)
    rows = []
    for s, c in cust_of.items():
        rc = returns.get(c, {}).get(month)
        if rc is not None:
            rows.append((s, c, rc))
    return sorted(rows, key=lambda r: (-r[2], r[0]))


def performance(series: dict) -> dict:
    """Annualized summary stats for a monthly return series."""
    xs = [series[k] for k in sorted(series)]
    n = len(xs)
    if n == 0:
        return {"n": 0}
    mu = mean(xs)
    sd = pstdev(xs) if n > 1 else 0.0
    return {
        "n": n,
        "mean_monthly": mu,
        "ann_return": mu * 12,
        "ann_vol": sd * sqrt(12),
        "sharpe": (mu / sd * sqrt(12)) if sd > 0 else float("nan"),
        "hit_rate": sum(1 for x in xs if x > 0) / n,
    }
