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


def _name_ok(ticker, raw, ticker_to_title, title_token_sets) -> tuple[bool, str]:
    """(ok, reason) for the customer name<->ticker mapping. Rejects generic names that match
    many companies (ambiguous) and, when the ticker is in the SEC map, titles unrelated to the
    extracted name (name_mismatch). A ticker absent from the domestic SEC map (foreign ADRs,
    some multi-class tickers) is NOT rejected on that basis alone — ambiguity still applies."""
    raw_tokens = set(norm(raw).split())
    if not raw_tokens:
        return False, "ambiguous"
    matches = sum(1 for toks in title_token_sets if raw_tokens <= toks)
    if matches > AMBIG_MAX:
        return False, "ambiguous"
    if ticker in ticker_to_title:
        sim = SequenceMatcher(None, norm(raw), norm(ticker_to_title[ticker])).ratio()
        if sim < NAME_SIM_MIN:
            return False, "name_mismatch"
    return True, ""


def validate_links(links, bars_fn=fetch_daily_bars, ticker_map=None) -> tuple[list, list]:
    """Partition links into (good, rejected). Each rejected link carries a 'reason'. Checks:
    supplier price-sanity, customer price-sanity, then customer name<->ticker (first failure wins)."""
    if ticker_map is None:
        ticker_map = load_ticker_map()
    by_cik, _ = ticker_map
    ticker_to_title = {v["ticker"]: v["title"] for v in by_cik.values()}
    title_token_sets = [set(norm(t).split()) for t in ticker_to_title.values()]

    cache: dict = {}
    def _bars(t):
        if t not in cache:
            try:
                cache[t] = bars_fn(t)
            except Exception:
                cache[t] = []
        return cache[t]

    good, rejected = [], []
    for lk in links:
        ok, reason = _price_ok(_bars(lk["supplier"]))
        if not ok:
            rejected.append({**lk, "reason": f"supplier_{reason}"}); continue
        ok, reason = _price_ok(_bars(lk["customer"]))
        if not ok:
            rejected.append({**lk, "reason": f"customer_{reason}"}); continue
        ok, reason = _name_ok(lk["customer"], lk.get("customer_raw", ""),
                              ticker_to_title, title_token_sets)
        if not ok:
            rejected.append({**lk, "reason": reason}); continue
        good.append(lk)
    return good, rejected
