"""Daily per-trade dynamic engine: signal-triggered entries, trailing-stop + signal exits.

Replaces the fixed monthly hold. Each supplier can hold one directional trade at a time:
- ENTER long if its customer's trailing-`LOOKBACK`-day return >= +ENTER; short if <= -ENTER.
- EXIT on whichever fires first:
    * trailing stop: stop = peak_trade_return - TRAIL (peak starts at 0, so this is also the
      -TRAIL initial watermark; it only ratchets up),
    * signal reversal: customer trailing return decays back through EXIT against the trade
      (hysteresis: ENTER > EXIT avoids whipsaw).
- No time cap. Params are frozen defaults, adjustable here — do NOT tune them on live data.
Pure stdlib. Marks daily (intraday later, once live with a real stop-order ladder).
"""
from __future__ import annotations

from statistics import mean

ENTER, EXIT, TRAIL, LOOKBACK = 0.05, 0.00, 0.05, 21


def _maps(prices: dict) -> dict:
    out = {}
    for t, series in prices.items():
        dates = [d for d, _ in series]
        pxs = [p for _, p in series]
        out[t] = {"px": dict(series), "dates": dates, "pxs": pxs}
    return out


def _trailing(m: dict, lookback: int) -> dict:
    tr, dates, pxs = {}, m["dates"], m["pxs"]
    for i in range(lookback, len(dates)):
        if pxs[i - lookback]:
            tr[dates[i]] = pxs[i] / pxs[i - lookback] - 1.0
    return tr


def simulate(links, prices, enter=ENTER, exit_=EXIT, trail=TRAIL, lookback=LOOKBACK):
    """Return (closed_trades, open_trades). Each trade: dict with side/entry/exit/ret/reason."""
    maps = _maps(prices)
    cust_of: dict[str, str] = {}
    for s, c in links:
        cust_of.setdefault(s, c)  # one principal customer per supplier
    tr = {c: _trailing(maps[c], lookback) for c in set(cust_of.values()) if c in maps}

    all_dates = sorted({d for s in cust_of for d in maps.get(s, {}).get("dates", [])})
    open_tr: dict[str, dict] = {}
    closed: list[dict] = []

    for d in all_dates:
        for s in list(open_tr):                     # manage open trades
            t, mp = open_tr[s], maps[s]
            if d not in mp["px"]:
                continue
            px = mp["px"][d]
            ret = t["side"] * (px / t["entry_px"] - 1.0)
            t["peak"] = max(t["peak"], ret)
            csig = tr.get(t["customer"], {}).get(d)
            reason = None
            if ret <= t["peak"] - trail:
                reason = "trail_stop"
            elif csig is not None and ((t["side"] > 0 and csig < exit_) or
                                       (t["side"] < 0 and csig > -exit_)):
                reason = "signal"
            if reason:
                t.update(exit_date=d, exit_px=px, ret=ret, reason=reason,
                         days=(d - t["entry_date"]).days)
                closed.append(t)
                del open_tr[s]

        for s, c in cust_of.items():                # scan for entries
            if s in open_tr or s not in maps or c not in maps or d not in maps[s]["px"]:
                continue
            csig = tr.get(c, {}).get(d)
            if csig is None:
                continue
            side = 1 if csig >= enter else (-1 if csig <= -enter else 0)
            if side:
                open_tr[s] = {"supplier": s, "customer": c, "side": side,
                              "entry_date": d, "entry_px": maps[s]["px"][d], "peak": 0.0}
    return closed, list(open_tr.values())


def trade_stats(closed: list[dict]) -> dict:
    n = len(closed)
    if not n:
        return {"n": 0}
    rets = [t["ret"] for t in closed]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    return {
        "n": n, "win_rate": len(wins) / n, "mean_ret": mean(rets),
        "avg_win": mean(wins) if wins else 0.0, "avg_loss": mean(losses) if losses else 0.0,
        "total": sum(rets), "avg_days": mean(t["days"] for t in closed),
        "stops": sum(t["reason"] == "trail_stop" for t in closed),
        "signals": sum(t["reason"] == "signal" for t in closed),
    }
