"""Phase-5 kill-rule scorecard (PLAN §11.8). Pure computation from paper_state.json — no I/O, no
LLM. Pass = net Sharpe >= 0.5 AND positive net expectancy AND >= 5 ideas/month, judged at the
later of 12 months after paper_start and >= 30 closed OOS trades. Display only; recommendations
only.
"""
from __future__ import annotations

from datetime import date
from statistics import mean, pstdev

SHARPE_MIN = 0.5
EXPECTANCY_MIN = 0.0
MIN_IDEAS_PER_MONTH = 5.0
MIN_MONTHS = 12
MIN_TRADES = 30
DAYS_PER_MONTH = 30.44
DAYS_PER_YEAR = 365.25


def sharpe(rets: list, years: float) -> float | None:
    """Per-trade net-return Sharpe annualized at the realized trade frequency:
    (mean / pstdev) * sqrt(n / years). None if < 2 trades, zero variance, or non-positive years.
    Per-trade — not a capital-weighted portfolio Sharpe."""
    if len(rets) < 2 or years <= 0:
        return None
    sd = pstdev(rets)
    if sd == 0:
        return None
    return (mean(rets) / sd) * ((len(rets) / years) ** 0.5)


def scorecard(state: dict, start: date, today: date) -> dict:
    """Live kill-rule scorecard. Never raises on empty/degenerate input."""
    closed = state.get("closed") or []
    opens = state.get("open") or []
    days = max((today - start).days, 0)
    months = days / DAYS_PER_MONTH
    years = days / DAYS_PER_YEAR
    n_closed = len(closed)
    n_ideas = n_closed + len(opens)
    rets = [c["ret_net"] for c in closed if "ret_net" in c]
    expectancy = mean(rets) if rets else None
    sharpe_val = sharpe(rets, years)
    ideas_per_month = (n_ideas / months) if months >= 1 else None
    gate_open = months >= MIN_MONTHS and n_closed >= MIN_TRADES
    sharpe_ok = sharpe_val is not None and sharpe_val >= SHARPE_MIN
    expectancy_ok = expectancy is not None and expectancy > EXPECTANCY_MIN
    volume_ok = ideas_per_month is not None and ideas_per_month >= MIN_IDEAS_PER_MONTH
    verdict = "PENDING" if not gate_open else (
        "PASS" if (sharpe_ok and expectancy_ok and volume_ok) else "FAIL")
    return {"verdict": verdict, "gate_open": gate_open, "months": months, "n_closed": n_closed,
            "n_ideas": n_ideas, "expectancy": expectancy, "sharpe": sharpe_val,
            "ideas_per_month": ideas_per_month, "sharpe_ok": sharpe_ok,
            "expectancy_ok": expectancy_ok, "volume_ok": volume_ok,
            "thresholds": {"sharpe": SHARPE_MIN, "expectancy": EXPECTANCY_MIN,
                           "ideas_per_month": MIN_IDEAS_PER_MONTH, "months": MIN_MONTHS,
                           "trades": MIN_TRADES}}


def _fmt(x, pct=False) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.2f}%" if pct else f"{x:.2f}"


def scorecard_line(sc: dict) -> str:
    """One-line plain-text summary for the email."""
    return (f"Kill rule: {sc['verdict']} · Sharpe {_fmt(sc['sharpe'])} · "
            f"exp {_fmt(sc['expectancy'], pct=True)}/trade · "
            f"{_fmt(sc['ideas_per_month'])} ideas/mo · "
            f"gate {sc['months']:.0f}/12mo, {sc['n_closed']}/30 trades")
