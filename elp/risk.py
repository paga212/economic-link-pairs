"""Risk/Borrow agent (Phase 3): per open idea, deterministic borrow / earnings-window / liquidity
facts, narrated by a thin Opus call. Soft-derates risky ideas in the digest. Numbers are computed
in code; the LLM only narrates. Fail-soft. Recommendations only.
"""
from __future__ import annotations

from datetime import date, timedelta

BORROW_MKTCAP_MIN = 2e9        # small-cap short borrow is often tight; crude proxy (no free feed)
BORROW_ADV_MIN = 20e6
CADENCE_DAYS = 91              # ~one fiscal quarter
ANNOUNCE_LAG = 40             # ~days from fiscal period end to the earnings announcement
HEDGE_ETF = "SPY"


def borrow_class(ticker, direction, instrument, marketcap, adv) -> str:
    """'na' unless the leg is a short stock; 'easy' for the broad ETF or a large, liquid name;
    else 'hard' (Grade-C market-cap + ADV proxy — there is no free borrow-fee feed)."""
    if not (instrument == "stock" and direction < 0):
        return "na"
    if ticker == HEDGE_ETF:
        return "easy"
    if marketcap is not None and marketcap >= BORROW_MKTCAP_MIN and adv >= BORROW_ADV_MIN:
        return "easy"
    return "hard"


def _latest(period_end_dates: list[str]):
    ds = sorted({date.fromisoformat(d[:10]) for d in period_end_dates if d}, reverse=True)
    return ds[0] if ds else None


def next_earnings_est(period_end_dates, today):
    """Estimated NEXT earnings-announcement date + days-to, from the latest fiscal period end.
    (None, None) if no dates. A cadence estimate, not the announced date."""
    last = _latest(period_end_dates)
    if last is None:
        return None, None
    last_announce = last + timedelta(days=ANNOUNCE_LAG)
    nxt = last_announce if last_announce >= today else last + timedelta(days=CADENCE_DAYS + ANNOUNCE_LAG)
    return nxt, (nxt - today).days


def reported_since_entry(period_end_dates, entry, today) -> bool:
    """Did the estimated most-recent announcement fall between entry and today (edge likely spent)?"""
    last = _latest(period_end_dates)
    if last is None:
        return False
    last_announce = last + timedelta(days=ANNOUNCE_LAG)
    return entry < last_announce <= today
