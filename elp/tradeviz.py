"""Per-trade detail viz: reconstruct each leg's price and the combined trade return over time and
render them as inline SVG. Pure (given bars); reuses the engine's return math. No deps, no JS.
"""
from __future__ import annotations

from datetime import date
from html import escape


def _scale(series, width, height, pad):
    xs = [i for s in series for (i, _) in s["pts"]]
    ys = [y for s in series for (_, y) in s["pts"]]
    if not xs or not ys:
        return None
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax == xmin:
        xmax = xmin + 1
    if ymax == ymin:
        ymax = ymin + 1

    def X(i):
        return pad + (i - xmin) / (xmax - xmin) * (width - 2 * pad)

    def Y(y):
        return height - pad - (y - ymin) / (ymax - ymin) * (height - 2 * pad)

    return X, Y, ymin, ymax


def svg_line(series, entry_idx=None, width=640, height=160, pad=24, labels=None) -> str:
    """One <svg> with a <polyline> per series (shared scale). entry_idx draws a vertical marker;
    labels -> a tiny legend. Empty input -> a 'no data' placeholder."""
    sc = _scale(series, width, height, pad)
    if sc is None:
        return (f'<svg viewBox="0 0 {width} {height}" class=chart>'
                f'<text x={width // 2} y={height // 2} text-anchor=middle class=muted>no data</text></svg>')
    X, Y, ymin, ymax = sc
    parts = [f'<svg viewBox="0 0 {width} {height}" class=chart>']
    if ymin <= 0 <= ymax:
        y0 = Y(0)
        parts.append(f'<line x1={pad} y1={y0:.1f} x2={width - pad} y2={y0:.1f} class=axis/>')
    if entry_idx is not None:
        ex = X(entry_idx)
        parts.append(f'<line x1={ex:.1f} y1={pad} x2={ex:.1f} y2={height - pad} class=entry/>')
    for s in series:
        pts = " ".join(f"{X(i):.1f},{Y(y):.1f}" for i, y in s["pts"])
        dash = ' stroke-dasharray="4 3"' if s.get("dash") else ""
        parts.append(f'<polyline points="{pts}" class="{s["cls"]}" fill=none{dash}/>')
    for k, lab in enumerate(labels or []):
        parts.append(f'<text x={pad + 2} y={pad + 12 + 14 * k} class=legend>{escape(lab)}</text>')
    parts.append("</svg>")
    return "".join(parts)


from elp.options import bear_put_spread          # noqa: E402
from elp.trades import RISK_FREE, idea_return     # noqa: E402


def _price_map(bars):
    return {d: px for d, px, _ in bars}


def combined_series(idea: dict, bars_by_ticker: dict) -> dict:
    """Combined trade return per unit primary notional at each common date, split at entry:
    solid (>= entry) and dashed (< entry, the hypothetical earlier hold). Reuses idea_return."""
    p, n = idea["primary"], idea["neutralizer"]
    entry = date.fromisoformat(idea["entry"])
    idea["entry_date"] = entry                    # idea_return reads this eagerly via setdefault
    pm = {t: _price_map(bars_by_ticker.get(t, [])) for t in (p["ticker"], n["ticker"])}
    dates = sorted(set(pm[p["ticker"]]) & set(pm[n["ticker"]]))
    solid, dashed, entry_idx = [], [], None
    for i, d in enumerate(dates):
        marks = {p["ticker"]: pm[p["ticker"]][d], n["ticker"]: pm[n["ticker"]][d]}
        ret, _ = idea_return(idea, marks, d)
        if d >= entry:
            if entry_idx is None:
                entry_idx = i
            solid.append((i, ret))
        else:
            dashed.append((i, ret))
    if dashed and solid:
        dashed.append(solid[0])                   # connect the dashed segment to the solid start
    return {"dates": dates, "solid": solid, "dashed": dashed, "entry_idx": entry_idx}


def leg_price_series(leg: dict, bars: list, entry: date) -> list:
    """Per-leg chart series: stock -> the underlying price; spread -> its repriced mark."""
    out = []
    for i, (d, px, _) in enumerate(bars):
        if leg["instrument"] == "spread":
            trem = max(leg["T0"] - (d - entry).days / 365.0, 1e-6)
            y = bear_put_spread(px, leg["k_long"], leg["k_short"], trem, leg["iv"], RISK_FREE)
        else:
            y = px
        out.append((i, y))
    return out
