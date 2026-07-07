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


def _date_ticks(dates, n=5):
    """Up to n evenly-spaced (index, date) ticks spanning the series, first and last included."""
    m = len(dates)
    if m == 0:
        return []
    if m == 1:
        return [(0, dates[0])]
    k = min(n, m)
    idxs = sorted({round(j * (m - 1) / (k - 1)) for j in range(k)})
    return [(i, dates[i]) for i in idxs]


def _axis_svg(X, dates, width, height, pad) -> str:
    """Bottom x-axis line + up to 5 '%b %d' date ticks. X: index->pixel. Empty dates -> ''."""
    ticks = _date_ticks(dates or [])
    if not ticks:
        return ""
    out = [f'<line x1={pad} y1={height - pad:.1f} x2={width - pad} y2={height - pad:.1f} class=axis />']
    for k, (i, d) in enumerate(ticks):
        x = X(i)
        anchor = "start" if k == 0 else ("end" if k == len(ticks) - 1 else "middle")
        out.append(f'<line x1={x:.1f} y1={height - pad:.1f} x2={x:.1f} y2={height - pad + 3:.1f} class=axis />')
        out.append(f'<text x={x:.1f} y={height - pad + 14:.1f} text-anchor={anchor} '
                   f'class=legend>{escape(d.strftime("%b %d"))}</text>')
    return "".join(out)


def _grid_svg(X, dates, height, pad) -> str:
    """Dashed vertical guide at each date tick (drawn behind the data so it stays recessive)."""
    return "".join(f'<line x1={X(i):.1f} y1={pad} x2={X(i):.1f} y2={height - pad:.1f} class=grid />'
                   for i, _ in _date_ticks(dates or []))


def _entry_svg(ex, width, height, pad) -> str:
    """Dashed vertical entry marker plus a small 'entry' label kept inside the plot."""
    anchor = "end" if ex > width * 0.6 else "start"
    dx = -3 if anchor == "end" else 3
    return (f'<line x1={ex:.1f} y1={pad} x2={ex:.1f} y2={height - pad:.1f} class=entry />'
            f'<text x={ex + dx:.1f} y={pad + 9} text-anchor={anchor} class=legend>entry</text>')


def _legend_svg(labels, pad) -> str:
    return "".join(f'<text x={pad + 2} y={pad + 12 + 14 * k} class=legend>{escape(lab)}</text>'
                   for k, lab in enumerate(labels or []))


def svg_line(series, entry_idx=None, width=640, height=160, pad=24, labels=None, dates=None) -> str:
    """One <svg> with a <polyline> per series (shared scale). entry_idx draws a vertical marker;
    labels -> a tiny legend; dates (index->date, aligned with each series' x index) -> a labelled
    x date axis. Empty input -> a 'no data' placeholder."""
    sc = _scale(series, width, height, pad)
    if sc is None:
        return (f'<svg viewBox="0 0 {width} {height}" class=chart>'
                f'<text x={width // 2} y={height // 2} text-anchor=middle class=muted>no data</text></svg>')
    X, Y, ymin, ymax = sc
    parts = [f'<svg viewBox="0 0 {width} {height}" class=chart>']
    parts.append(_grid_svg(X, dates, height, pad))
    if ymin <= 0 <= ymax:
        y0 = Y(0)
        parts.append(f'<line x1={pad} y1={y0:.1f} x2={width - pad} y2={y0:.1f} class=axis />')
    if entry_idx is not None:
        parts.append(_entry_svg(X(entry_idx), width, height, pad))
    for s in series:
        pts = " ".join(f"{X(i):.1f},{Y(y):.1f}" for i, y in s["pts"])
        dash = ' stroke-dasharray="4 3"' if s.get("dash") else ""
        parts.append(f'<polyline points="{pts}" class="{s["cls"]}" fill=none{dash} />')
    if series and series[-1]["pts"]:                 # dot the latest value of the topmost series
        li, ly = series[-1]["pts"][-1]
        parts.append(f'<circle cx={X(li):.1f} cy={Y(ly):.1f} r=2.6 class="{series[-1]["cls"]}" '
                     f'style="fill:currentColor" />')
    parts.append(_axis_svg(X, dates, width, height, pad))
    parts.append(_legend_svg(labels, pad))
    parts.append("</svg>")
    return "".join(parts)


def svg_candles(bars, entry_idx=None, width=640, height=160, pad=24, labels=None, dates=None) -> str:
    """OHLC candlesticks from (date, open, high, low, close, vol) bars: a low->high wick and an
    open->close body per bar, coloured up/down. Same axis/legend/entry chrome as svg_line."""
    if not bars:
        return (f'<svg viewBox="0 0 {width} {height}" class=chart>'
                f'<text x={width // 2} y={height // 2} text-anchor=middle class=muted>no data</text></svg>')
    lo = min(b[3] for b in bars)
    hi = max(b[2] for b in bars)
    if hi == lo:
        hi = lo + 1
    n = len(bars)
    span = (n - 1) or 1

    def X(i):
        return pad + i / span * (width - 2 * pad)

    def Y(y):
        return height - pad - (y - lo) / (hi - lo) * (height - 2 * pad)

    bw = max(1.5, 0.6 * (width - 2 * pad) / n)
    parts = [f'<svg viewBox="0 0 {width} {height}" class=chart>']
    parts.append(_grid_svg(X, dates, height, pad))
    if entry_idx is not None:
        parts.append(_entry_svg(X(entry_idx), width, height, pad))
    for i, (d, o, h, low, c, _v) in enumerate(bars):
        x = X(i)
        cls = "up" if c >= o else "down"
        parts.append(f'<line x1={x:.1f} y1={Y(h):.1f} x2={x:.1f} y2={Y(low):.1f} class=wick />')
        top, bot = Y(max(o, c)), Y(min(o, c))
        parts.append(f'<rect x={x - bw / 2:.1f} y={top:.1f} width={bw:.1f} '
                     f'height={max(bot - top, 1):.1f} class={cls} />')
    parts.append(_axis_svg(X, dates, width, height, pad))
    parts.append(_legend_svg(labels, pad))
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
    "svg.chart{width:100%;height:auto;background:#fcfcfd;border:1px solid #ececf0;border-radius:6px}"
    ".leg{stroke:#2563c9;color:#2563c9;stroke-width:1.8;stroke-linejoin:round;stroke-linecap:round}"
    ".pv{stroke:#0f9d63;color:#0f9d63;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}"
    ".wick{stroke:#9aa0a6;stroke-width:1}.up{fill:#0f9d63;stroke:#0f9d63}.down{fill:#e0503a;stroke:#e0503a}"
    ".grid{stroke:#ededf1;stroke-width:1;stroke-dasharray:3 3}"
    ".axis{stroke:#d7d7dd;stroke-width:1}.entry{stroke:#c0392b;stroke-width:1;stroke-dasharray:3 3}"
    ".legend{fill:#8a8f98;font-size:11px}table{border-collapse:collapse;width:100%;margin:.3rem 0;"
    "font-size:.9rem}th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid #eee}")


def _leg_row(leg: dict, bars: list, expression: str) -> str:
    latest = f'{bars[-1][1]:.2f}' if bars else "—"
    return (f'<tr><td>{escape(leg["ticker"])}</td>'
            f'<td>{"long" if leg["direction"] > 0 else "short"}</td>'
            f'<td class=sub>{escape(describe_leg(leg, expression))}</td>'
            f'<td>{leg.get("entry_px", 0.0):.2f}</td><td>{latest}</td></tr>')


def trade_detail_html(idea: dict, bars_by_ticker: dict, ohlc_by_ticker: dict = None) -> str:
    """One trade block: header + per-leg charts + combined chart + table. Fail-soft per leg.
    Stock legs render as OHLC candlesticks when ohlc_by_ticker has bars for them; spread legs
    (a modelled mark, no OHLC) stay a line."""
    ohlc_by_ticker = ohlc_by_ticker or {}
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
        ohlc = ohlc_by_ticker.get(leg["ticker"], [])
        if leg["instrument"] != "spread" and ohlc:
            chart = svg_candles(ohlc, entry_idx=eidx, labels=[f'{leg["ticker"]} price (OHLC)'],
                                dates=[b[0] for b in ohlc])
        else:
            lab = f'{leg["ticker"]} {"spread mark" if leg["instrument"] == "spread" else "price"}'
            chart = svg_line([{"pts": leg_price_series(leg, bars, entry), "cls": "leg", "dash": False}],
                             entry_idx=eidx, labels=[lab], dates=[b[0] for b in bars])
        leg_charts += '<div class=chartbox>' + chart + '</div>'

    cs = combined_series(idea, bars_by_ticker)
    if cs["solid"] or cs["dashed"]:
        series = []
        if cs["dashed"]:
            series.append({"pts": cs["dashed"], "cls": "pv", "dash": True})
        if cs["solid"]:
            series.append({"pts": cs["solid"], "cls": "pv", "dash": False})
        combined = ('<div class=chartbox>'
                    + svg_line(series, entry_idx=cs["entry_idx"], dates=cs["dates"],
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
