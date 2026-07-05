"""Compact Black-Scholes for the bear-put-spread short leg (Grade-C: proxied IV, no skew).

Lets SHORT trades be expressed as defined-risk bear put spreads (no stock borrow) instead
of shorting the stock. Model-priced from trailing realized vol as an IV proxy — an
APPROXIMATION pending real options data (research/07, PLAN §11.5): European BS, no skew,
no early exercise, no real bid/ask. Treat results as an upper bound. Pure stdlib.
"""
from math import erf, exp, log, sqrt


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def bs_put(S: float, K: float, T: float, iv: float, r: float = 0.04) -> float:
    """Black-Scholes European put price."""
    if T <= 0 or iv <= 0:
        return max(K - S, 0.0)
    v = iv * sqrt(T)
    d1 = (log(S / K) + (r + 0.5 * iv * iv) * T) / v
    return K * exp(-r * T) * _cdf(-(d1 - v)) - S * _cdf(-d1)


def bear_put_spread(S: float, K1: float, K2: float, T: float, iv: float, r: float = 0.04) -> float:
    """Long higher-strike put K1, short lower-strike put K2 (K2 < K1) — profits as S falls.
    Value is bounded in [0, K1-K2]."""
    return bs_put(S, K1, T, iv, r) - bs_put(S, K2, T, iv, r)


def snap_strike(px: float) -> float:
    """Nearest listed strike on a realistic grid: $0.50 under $25, $1 under $200, $5 above."""
    step = 0.5 if px < 25 else (1.0 if px < 200 else 5.0)
    return round(px / step) * step
