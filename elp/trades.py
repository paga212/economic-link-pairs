"""Daily per-trade dynamic engine: signal-triggered entries, trailing-stop + signal exits.

Each supplier can hold one directional trade at a time:
- ENTER long if its customer's trailing-`LOOKBACK`-day return >= +ENTER; short if <= -ENTER.
- LONG = cash stock. SHORT = a defined-risk BEAR PUT SPREAD by default (no stock borrow),
  priced with Black-Scholes off trailing realized vol as an IV proxy (Grade-C, approximate;
  see elp/options.py). Set short_mode="stock" to short the stock instead (borrow charged).
- EXIT on whichever fires first: trailing stop (stop = peak_return - TRAIL, ratchets up from
  the -TRAIL watermark), signal reversal (customer trailing return back through EXIT, with
  ENTER>EXIT hysteresis), or — for spreads — option expiry.
- No time cap. Frozen params — do NOT tune on live data. Pure stdlib; daily marks.
"""
from __future__ import annotations

from math import log, sqrt
from statistics import mean, pstdev

from elp.options import bear_put_spread

ENTER, EXIT, TRAIL, LOOKBACK = 0.05, 0.00, 0.05, 21
SHORT_MODE = "spread"                       # "spread" (bear put, no borrow) or "stock"
SPREAD_WIDTH, DTE, RISK_FREE, VOL_LB = 0.10, 45, 0.04, 63

# Cost knobs (conservative, frozen — NOT tuned). No name-level borrow data, so BORROW_APR
# is a deliberately-high flat proxy for shorting small caps (only used for stock shorts).
SPREAD_BPS = 25.0    # per side (spread/2 + commission); charged on entry AND exit
BORROW_APR = 0.05    # annualized borrow, STOCK shorts only, prorated by holding days


def net_return(t: dict, spread_bps: float = SPREAD_BPS, borrow_apr: float = BORROW_APR) -> float:
    """Trade return net of round-trip transaction cost and (stock shorts only) borrow."""
    tc = 2.0 * spread_bps / 1e4
    is_stock_short = t["side"] < 0 and t.get("instrument", "stock") == "stock"
    borrow = (borrow_apr * t["days"] / 365.0) if is_stock_short else 0.0
    return t["ret"] - tc - borrow


def _maps(prices: dict) -> dict:
    out = {}
    for t, series in prices.items():
        dates = [d for d, _ in series]
        pxs = [p for _, p in series]
        out[t] = {"px": dict(series), "dates": dates, "pxs": pxs,
                  "idx": {d: k for k, d in enumerate(dates)}}
    return out


def _trailing(m: dict, lookback: int) -> dict:
    tr, dates, pxs = {}, m["dates"], m["pxs"]
    for i in range(lookback, len(dates)):
        if pxs[i - lookback]:
            tr[dates[i]] = pxs[i] / pxs[i - lookback] - 1.0
    return tr


def _vol(m: dict, i: int, lb: int = VOL_LB) -> float:
    """Annualized realized vol from the last `lb` daily log returns ending at index i."""
    pxs = m["pxs"]
    rs = [log(pxs[k] / pxs[k - 1]) for k in range(max(1, i - lb), i + 1)
          if pxs[k - 1] > 0 and pxs[k] > 0]
    return pstdev(rs) * sqrt(252) if len(rs) >= 5 else 0.4


def _mark(t: dict, px: float, d) -> tuple[float, bool]:
    """(trade return, expired?) for the current price."""
    if t["instrument"] == "spread":
        elapsed = (d - t["entry_date"]).days
        trem = max(t["T0"] - elapsed / 365.0, 1e-6)
        val = bear_put_spread(px, t["K1"], t["K2"], trem, t["iv"], RISK_FREE)
        return (val - t["debit"]) / t["S0"], elapsed >= t["dte"]
    return t["side"] * (px / t["entry_px"] - 1.0), False


def simulate(links, prices, enter=ENTER, exit_=EXIT, trail=TRAIL, lookback=LOOKBACK,
             short_mode=SHORT_MODE):
    """Return (closed_trades, open_trades). Longs = cash stock; shorts = bear put spread
    (or stock if short_mode='stock')."""
    maps = _maps(prices)
    cust_of: dict[str, str] = {}
    for s, c in links:
        cust_of.setdefault(s, c)
    tr = {c: _trailing(maps[c], lookback) for c in set(cust_of.values()) if c in maps}

    all_dates = sorted({d for s in cust_of for d in maps.get(s, {}).get("dates", [])})
    open_tr: dict[str, dict] = {}
    closed: list[dict] = []

    for d in all_dates:
        for s in list(open_tr):
            t, mp = open_tr[s], maps[s]
            if d not in mp["px"]:
                continue
            px = mp["px"][d]
            ret, expired = _mark(t, px, d)
            t["peak"] = max(t["peak"], ret)
            csig = tr.get(t["customer"], {}).get(d)
            reason = None
            if ret <= t["peak"] - trail:
                reason = "trail_stop"
            elif csig is not None and ((t["side"] > 0 and csig < exit_) or
                                       (t["side"] < 0 and csig > -exit_)):
                reason = "signal"
            elif expired:
                reason = "expiry"
            if reason:
                t.update(exit_date=d, exit_px=px, ret=ret, reason=reason,
                         days=(d - t["entry_date"]).days)
                closed.append(t)
                del open_tr[s]

        for s, c in cust_of.items():
            if s in open_tr or s not in maps or c not in maps or d not in maps[s]["px"]:
                continue
            csig = tr.get(c, {}).get(d)
            if csig is None:
                continue
            side = 1 if csig >= enter else (-1 if csig <= -enter else 0)
            if not side:
                continue
            s0 = maps[s]["px"][d]
            trade = {"supplier": s, "customer": c, "side": side, "entry_date": d,
                     "entry_px": s0, "peak": 0.0, "instrument": "stock"}
            if side < 0 and short_mode == "spread":
                iv = _vol(maps[s], maps[s]["idx"][d])
                k1, k2, t0 = s0, s0 * (1 - SPREAD_WIDTH), DTE / 365.0
                trade.update(instrument="spread", S0=s0, K1=k1, K2=k2, T0=t0, iv=iv, dte=DTE,
                             debit=bear_put_spread(s0, k1, k2, t0, iv, RISK_FREE))
            open_tr[s] = trade
    return closed, list(open_tr.values())


def trade_stats(closed: list[dict], spread_bps: float = 0.0, borrow_apr: float = 0.0) -> dict:
    """Trade-level stats. Default (0,0) = gross; pass costs for net (SPREAD_BPS/BORROW_APR)."""
    n = len(closed)
    if not n:
        return {"n": 0}
    rets = [net_return(t, spread_bps, borrow_apr) for t in closed]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    return {
        "n": n, "win_rate": len(wins) / n, "mean_ret": mean(rets),
        "avg_win": mean(wins) if wins else 0.0, "avg_loss": mean(losses) if losses else 0.0,
        "total": sum(rets), "avg_days": mean(t["days"] for t in closed),
        "stops": sum(t["reason"] == "trail_stop" for t in closed),
        "signals": sum(t["reason"] == "signal" for t in closed),
        "expiries": sum(t["reason"] == "expiry" for t in closed),
    }
