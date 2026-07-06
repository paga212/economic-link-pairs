"""Risk/Borrow agent (Phase 3): per open idea, deterministic borrow / earnings-window / liquidity
facts, narrated by a thin Opus call. Soft-derates risky ideas in the digest. Numbers are computed
in code; the LLM only narrates. Fail-soft. Recommendations only.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from elp.liquidity import dollar_adv, is_tradeable
from elp.llm import AnthropicError, complete, parse_json  # noqa: F401  (parse_json kept for symmetry)
from elp.tiingo import fetch_daily_bars, fetch_marketcap, fetch_statement_dates

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


OPUS = "claude-opus-4-8"

_NARRATE_SYS = (
    "You are a risk analyst for a customer-supplier lead-lag paper-trade. Given pre-computed risk "
    "facts, write ONE short plain sentence for the reader. Never add or change a number. "
    "Recommendations only.")


def _safe_bars(bars_fn, t):
    try:
        return bars_fn(t) or []
    except Exception:
        return []


def _short_stock_leg(idea: dict):
    for role in ("primary", "neutralizer"):
        leg = idea.get(role) or {}
        if leg.get("instrument") == "stock" and leg.get("direction", 0) < 0:
            return leg
    return None


def assess_idea_risk(idea, bars_fn=fetch_daily_bars, mktcap_fn=fetch_marketcap,
                     dates_fn=fetch_statement_dates, today=None) -> dict:
    """Deterministic borrow / earnings-window / liquidity facts. Every fetch is fail-soft, so
    missing data yields conservative labels rather than a raise."""
    today = today or datetime.now(timezone.utc).date()
    sup = idea["supplier"]
    liquidity = "ok" if is_tradeable(_safe_bars(bars_fn, sup)) else "thin"

    leg = _short_stock_leg(idea)
    if leg:
        t = leg["ticker"]
        try:
            mc = mktcap_fn(t)
        except Exception:
            mc = None
        bclass = borrow_class(t, leg["direction"], leg["instrument"], mc,
                              dollar_adv(_safe_bars(bars_fn, t)))
        borrow = {"ticker": t, "class": bclass}
    else:
        borrow = {"ticker": None, "class": "na"}

    try:
        dates = dates_fn(sup)
    except Exception:
        dates = []
    _, days_to = next_earnings_est(dates, today)
    try:
        entry = date.fromisoformat(idea["entry"]) if idea.get("entry") else None
    except (ValueError, TypeError):
        entry = None
    rse = reported_since_entry(dates, entry, today) if entry else False

    return {"borrow": borrow, "earnings": {"days_to": days_to, "reported_since_entry": rse},
            "liquidity": liquidity}


def narrate(idea: dict, facts: dict) -> str:
    """One Opus sentence from the computed facts; adds no numbers. '' on any error (fail soft)."""
    try:
        prompt = (f"Idea: supplier {idea['supplier']} vs customer {idea['customer']}. Risk facts:\n"
                  f"{json.dumps(facts)}\n"
                  "Write one short sentence on borrow / earnings-timing / liquidity risk. If borrow "
                  "class is 'hard', note the short can still be put on via options (a put spread).")
        return complete(prompt, model=OPUS, system=_NARRATE_SYS, max_tokens=256).strip()
    except Exception:
        return ""


def build_risk(state: dict) -> dict:
    per = {}
    for o in state.get("open", []):
        try:
            facts = assess_idea_risk(o)
            facts["note"] = narrate(o, facts)
        except Exception:
            facts = {"borrow": {"ticker": None, "class": "na"},
                     "earnings": {"days_to": None, "reported_since_entry": False},
                     "liquidity": "ok", "note": ""}
        per[f'{o.get("supplier")}|{o.get("customer")}'] = facts
    return {"generated_utc": datetime.now(timezone.utc).isoformat(), "model_used": OPUS,
            "per_idea": per}


def risk_flag(rv: dict | None) -> str:
    """Short reader-facing flag, shared by dashboard + email. Precedence: borrow > earnings > liq."""
    if not rv:
        return ""
    if (rv.get("borrow") or {}).get("class") == "hard":
        return "⚠ hard to borrow — short via options"
    if (rv.get("earnings") or {}).get("reported_since_entry"):
        return "⚠ post-earnings (edge likely spent)"
    if rv.get("liquidity") == "thin":
        return "⚠ thin liquidity"
    return ""
