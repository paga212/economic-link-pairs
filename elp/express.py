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
        b = beta(bars[view["supplier"]], bars[HEDGE_ETF]) if HEDGE_ETF in bars else 1.0
        neutralizer = {"role": "neutralizer", "ticker": HEDGE_ETF, "direction": -view["side"],
                       "instrument": "stock", "notional": notional * b,    # beta-neutral
                       "entry_px": bars[HEDGE_ETF][-1][1]}
        expression = "stock-hedge"
    return {"supplier": view["supplier"], "customer": view["customer"], "side": view["side"],
            "entry_date": day, "primary": primary, "neutralizer": neutralizer,
            "expression": expression, "risk_cap": "soft", "peak": 0.0}
