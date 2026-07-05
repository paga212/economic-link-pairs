"""Liquidity + hedge-ratio primitives from daily (date, price, volume) bars. Pure stdlib.

Dollar-ADV gates which names are tradeable/optionable; beta sizes a beta-neutral ETF hedge.
"""
from __future__ import annotations

from statistics import mean

MIN_PRICE, MIN_ADV = 5.0, 5_000_000.0


def dollar_adv(bars: list[tuple], window: int = 63) -> float:
    """Mean dollar volume (price x volume) over the last `window` bars."""
    tail = bars[-window:]
    if not tail:
        return 0.0
    return mean(px * vol for _, px, vol in tail)


def is_tradeable(bars: list[tuple], min_price: float = MIN_PRICE, min_adv: float = MIN_ADV) -> bool:
    """Last price >= floor and dollar-ADV >= floor. Drops penny/illiquid names (and junk links)."""
    if not bars:
        return False
    last_px = bars[-1][1]
    return last_px >= min_price and dollar_adv(bars) >= min_adv


def _rets(bars: list[tuple]) -> dict:
    """date -> simple daily return."""
    out = {}
    for i in range(1, len(bars)):
        p0, p1 = bars[i - 1][1], bars[i][1]
        if p0 > 0:
            out[bars[i][0]] = p1 / p0 - 1.0
    return out


def beta(a_bars: list[tuple], b_bars: list[tuple], window: int = 63) -> float:
    """Trailing beta of a vs b over overlapping dates (cov/var). 1.0 if too little data."""
    ra, rb = _rets(a_bars), _rets(b_bars)
    common = sorted(set(ra) & set(rb))[-window:]
    if len(common) < 20:
        return 1.0
    xs = [rb[d] for d in common]
    ys = [ra[d] for d in common]
    mx, my = mean(xs), mean(ys)
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0:
        return 1.0
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / var
