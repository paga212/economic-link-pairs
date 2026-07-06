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


from elp.express import describe_leg              # noqa: E402

PAGE_CSS = (
    "body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:2rem auto;"
    "padding:0 1rem;color:#1a1a1a}h1{font-size:1.4rem}h2{font-size:1.05rem;margin:1.4rem 0 .3rem}"
    ".sub,.muted{color:#666}.muted{font-style:italic}"
    ".trade{border-top:1px solid #eee;padding-top:.6rem;margin-top:1.2rem}.chartbox{margin:.4rem 0}"
    "svg.chart{width:100%;height:auto;background:#fafafa;border:1px solid #eee;border-radius:4px}"
    ".leg{stroke:#1155cc;stroke-width:1.5}.pv{stroke:#0a7a3f;stroke-width:1.8}"
    ".axis{stroke:#ddd;stroke-width:1}.entry{stroke:#b02020;stroke-width:1;stroke-dasharray:2 2}"
    ".legend{fill:#666;font-size:11px}table{border-collapse:collapse;width:100%;margin:.3rem 0;"
    "font-size:.9rem}th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid #eee}")


def _leg_row(leg: dict, bars: list, expression: str) -> str:
    latest = f'{bars[-1][1]:.2f}' if bars else "—"
    return (f'<tr><td>{escape(leg["ticker"])}</td>'
            f'<td>{"long" if leg["direction"] > 0 else "short"}</td>'
            f'<td class=sub>{escape(describe_leg(leg, expression))}</td>'
            f'<td>{leg.get("entry_px", 0.0):.2f}</td><td>{latest}</td></tr>')


def trade_detail_html(idea: dict, bars_by_ticker: dict) -> str:
    """One trade block: header + per-leg charts + combined chart + table. Fail-soft per leg."""
    p, n = idea["primary"], idea["neutralizer"]
    entry = date.fromisoformat(idea["entry"])
    direction = "LONG" if idea["side"] > 0 else "SHORT"
    head = (f'<h2>{direction} {escape(idea["supplier"])} '
            f'<span class=sub>vs {escape(idea["customer"])} · {escape(idea["expression"])}</span></h2>'
            f'<p class=sub>primary: {escape(describe_leg(p, idea["expression"]))}<br>'
            f'neutralizer: {escape(describe_leg(n, idea["expression"]))}</p>')

    leg_charts = ""
    for leg in (p, n):
        bars = bars_by_ticker.get(leg["ticker"], [])
        if not bars:
            leg_charts += f'<p class=muted>{escape(leg["ticker"])}: no price data</p>'
            continue
        eidx = next((i for i, b in enumerate(bars) if b[0] >= entry), None)
        lab = f'{leg["ticker"]} {"spread mark" if leg["instrument"] == "spread" else "price"}'
        leg_charts += ('<div class=chartbox>'
                       + svg_line([{"pts": leg_price_series(leg, bars, entry), "cls": "leg", "dash": False}],
                                  entry_idx=eidx, labels=[lab]) + '</div>')

    cs = combined_series(idea, bars_by_ticker)
    if cs["solid"] or cs["dashed"]:
        series = []
        if cs["dashed"]:
            series.append({"pts": cs["dashed"], "cls": "pv", "dash": True})
        if cs["solid"]:
            series.append({"pts": cs["solid"], "cls": "pv", "dash": False})
        combined = ('<div class=chartbox>'
                    + svg_line(series, entry_idx=cs["entry_idx"],
                               labels=["combined return % (dashed = hypothetical pre-entry)"]) + '</div>')
        last = cs["solid"][-1][1] if cs["solid"] else cs["dashed"][-1][1]
        pnl = last * p["notional"]
        table = ('<table><tr><th>Leg</th><th>Dir</th><th>Size</th><th>Entry px</th><th>Latest px</th></tr>'
                 + _leg_row(p, bars_by_ticker.get(p["ticker"], []), idea["expression"])
                 + _leg_row(n, bars_by_ticker.get(n["ticker"], []), idea["expression"])
                 + f'<tr><td colspan=5 class=sub>combined: return <b>{last * 100:+.2f}%</b> · '
                   f'P&amp;L <b>{pnl / 1000:+.1f}k</b> on ${p["notional"] / 1000:.0f}k primary notional</td></tr></table>')
    else:
        combined = '<p class=muted>not enough overlapping price history to chart this trade.</p>'
        table = ""

    caveat = ('<p class=muted>Spread marks are Grade-C (flat IV). The pre-entry dashed line is a '
              'hypothetical mark of the fixed structure at earlier dates.</p>')
    return f'<section class=trade>{head}{leg_charts}{combined}{table}{caveat}</section>'
