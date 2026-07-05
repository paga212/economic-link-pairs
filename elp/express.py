"""Expression selector: turn a directional view into a two-legged idea (primary + neutralizer),
choosing a stock pair vs an ETF hedge by liquidity, risk-budgeted to $10k max drawdown.

CASH expressions only (long stock; short defined-risk bear-put-spread). The options overlay
(bull-call-spread, optionability-driven selection, $10k-premium leverage) is a later plan.
Pure stdlib. No number here comes from an LLM.
"""
from __future__ import annotations

from elp.liquidity import beta, is_tradeable
from elp.options import bear_put_spread, snap_strike
from elp.trades import DTE, RISK_FREE, SPREAD_WIDTH, TRAIL

RISK_BUDGET = 10_000.0      # max drawdown per idea (soft, stop-based for cash)
HEDGE_ETF = "SPY"           # broad-market hedge; sector-extensible later
STOP = TRAIL                # cash notional = RISK_BUDGET / STOP
BETA_MIN, BETA_MAX = 0.3, 3.0   # bound the ETF-hedge beta: a noisy trailing estimate
                                # (e.g. PG's ~0.01 in a low-vol window) must not size a
                                # near-useless (or absurd/negative) hedge leg


def _clamp_beta(b: float) -> float:
    """Bound the hedge beta to a sane band so a degenerate trailing estimate can't produce a
    near-zero (or absurdly large / negative) neutralizing leg."""
    return min(max(b, BETA_MIN), BETA_MAX)


def _primary_leg(view: dict) -> dict:
    """Cash primary leg: long stock, or short bear-put-spread with snapped strikes."""
    notional = RISK_BUDGET / STOP
    if view["side"] > 0:
        return {"role": "primary", "ticker": view["supplier"], "direction": 1,
                "instrument": "stock", "notional": notional, "entry_px": view["entry_px"]}
    s0 = view["entry_px"]
    k_long = snap_strike(s0)
    k_short = snap_strike(s0 * (1 - SPREAD_WIDTH))
    t0 = DTE / 365.0
    debit = bear_put_spread(s0, k_long, k_short, t0, view["iv"], RISK_FREE)
    return {"role": "primary", "ticker": view["supplier"], "direction": -1,
            "instrument": "spread", "notional": notional, "entry_px": s0,
            "S0": s0, "k_long": k_long, "k_short": k_short, "T0": t0,
            "iv": view["iv"], "dte": DTE, "debit": debit}


def _pick_counterpart(view: dict, bars: dict, signaling: dict, used: set):
    """Best opposite-signal, liquid, unused supplier — strongest |signal|, then ticker."""
    want = -view["side"]                          # neutralizer direction = opposite the primary
    cands = [(abs(sig), t) for t, sig in signaling.items()
             if t != view["supplier"] and t not in used
             and (sig > 0) == (want > 0) and t in bars and is_tradeable(bars[t])]
    if not cands:
        return None
    cands.sort(key=lambda x: (-x[0], x[1]))
    return cands[0][1]


def build_idea(view: dict, day, bars: dict, signaling: dict, used: set) -> dict:
    """Two-legged idea: primary leg + a pair-counterpart or ETF-hedge neutralizer."""
    primary = _primary_leg(view)
    notional = primary["notional"]
    cp = _pick_counterpart(view, bars, signaling, used)
    if cp is not None:
        neutralizer = {"role": "neutralizer", "ticker": cp, "direction": -view["side"],
                       "instrument": "stock", "notional": notional,        # dollar-neutral
                       "entry_px": bars[cp][-1][1]}
        expression = "stock-pair"
    else:
        b = _clamp_beta(beta(bars[view["supplier"]], bars[HEDGE_ETF])) if HEDGE_ETF in bars else 1.0
        neutralizer = {"role": "neutralizer", "ticker": HEDGE_ETF, "direction": -view["side"],
                       "instrument": "stock", "notional": notional * b,    # beta-neutral
                       "entry_px": bars[HEDGE_ETF][-1][1]}
        expression = "stock-hedge"
    return {"supplier": view["supplier"], "customer": view["customer"], "side": view["side"],
            "entry_date": day, "primary": primary, "neutralizer": neutralizer,
            "expression": expression, "risk_cap": "soft", "peak": 0.0}


def _money(x: float) -> str:
    """Compact approximate dollars: '≈$5.0k' for thousands, '≈$740' below."""
    return f"≈${x / 1000:.1f}k" if x >= 1000 else f"≈${x:.0f}"


def describe_leg(leg: dict, expression: str = "") -> str:
    """Human-readable one-line description of a leg, shared by the dashboard and the email so
    they can't drift. Exact share count for stock; for a bear-put-spread, the explicit structure
    (buy the higher-strike put, sell the lower), an implied contract count, and max risk. Every
    figure is derived from the leg's own notional/price fields — none comes from an LLM. The
    contract count and max risk are `≈` because the spread is a $200k-notional Grade-C model,
    not a literally-sized order."""
    notl, px = leg["notional"], leg["entry_px"]
    if leg["instrument"] == "spread":
        spot = leg.get("S0", px)
        contracts = max(1, round(notl / (100 * spot)))
        max_risk = contracts * leg["debit"] * 100
        return (f'bear put spread on {leg["ticker"]} (short): '
                f'buy {leg["k_long"]:.0f}P / sell {leg["k_short"]:.0f}P · '
                f'≈{contracts} spreads · ${leg["debit"]:.2f} debit · exp {leg["dte"]}d · '
                f'{_money(max_risk)} max risk')
    shares = round(notl / px) if px else 0
    side = "long" if leg["direction"] > 0 else "short"
    tag = ""
    if leg.get("role") == "neutralizer":
        tag = " · pair" if expression == "stock-pair" else " · β-hedge"
    return f'{side} {shares:,} sh {leg["ticker"]} @ ${px:.2f} (${notl / 1000:.0f}k{tag})'
