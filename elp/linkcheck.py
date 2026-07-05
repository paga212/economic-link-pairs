"""Validate customer-supplier links: quarantine wrong-ticker resolutions and glitchy/illiquid
price data before they reach the live universe. Reuses the liquidity gate, price bars, and the
SEC ticker map. Dependency-injected so unit tests run offline. Pure stdlib.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from elp.edgar import load_ticker_map, norm
from elp.liquidity import is_tradeable
from elp.tiingo import fetch_daily_bars

GAP_MAX = 5.0        # max adjacent-bar price ratio before a series is "glitchy"
NAME_SIM_MIN = 0.6   # difflib ratio floor for customer_raw vs the ticker's real title
AMBIG_MAX = 3        # max SEC titles a customer_raw may match before it's "ambiguous"


def _price_ok(bars) -> tuple[bool, str]:
    """(ok, reason) for a (date,price,volume) series: tradeable and free of absurd jumps."""
    if not bars:
        return False, "no_data"
    if not is_tradeable(bars):
        return False, "illiquid"
    for i in range(1, len(bars)):
        p0, p1 = bars[i - 1][1], bars[i][1]
        if p0 > 0 and p1 > 0 and (p1 / p0 > GAP_MAX or p0 / p1 > GAP_MAX):
            return False, "bad_bars"
    return True, ""
