"""Cohen-Frazzini signal-direction test (Phase 0).

The tradable claim is UNDER-REACTION: a customer's return in month M predicts the
supplier's return in month M+1 (a positive *lagged* relationship), distinct from the
two simply moving together contemporaneously. Phase 0 checks only the SIGN of that
lagged relationship on known pairs — it is not a backtest.
"""
from __future__ import annotations

from statistics import correlation, mean

Returns = dict[tuple[int, int], float]


def _next_month(key: tuple[int, int]) -> tuple[int, int]:
    y, m = key
    return (y, m + 1) if m < 12 else (y + 1, 1)


def lagged_pairs(cust: Returns, supp: Returns) -> tuple[list[float], list[float]]:
    """(customer month-M return, supplier month-(M+1) return) over aligned months."""
    xs, ys = [], []
    for key, rc in cust.items():
        nxt = _next_month(key)
        if nxt in supp:
            xs.append(rc)
            ys.append(supp[nxt])
    return xs, ys


def _corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return float("nan")
    return correlation(xs, ys)


def contemporaneous_corr(cust: Returns, supp: Returns) -> float:
    """Same-month correlation — high if the economic link moves the two together."""
    common = [(cust[k], supp[k]) for k in cust if k in supp]
    return _corr([a for a, _ in common], [b for _, b in common])


def evaluate_pair(cust: Returns, supp: Returns) -> dict | None:
    """Lagged predictive + contemporaneous stats; None if <12 aligned lagged months."""
    xs, ys = lagged_pairs(cust, supp)
    n = len(xs)
    if n < 12:
        return None
    up = [y for x, y in zip(xs, ys) if x > 0]
    dn = [y for x, y in zip(xs, ys) if x < 0]
    return {
        "n": n,
        "contemp_corr": contemporaneous_corr(cust, supp),
        "lagged_corr": _corr(xs, ys),
        "up_mean": mean(up) if up else float("nan"),
        "dn_mean": mean(dn) if dn else float("nan"),
        "up_minus_down": (mean(up) if up else 0.0) - (mean(dn) if dn else 0.0),
    }
