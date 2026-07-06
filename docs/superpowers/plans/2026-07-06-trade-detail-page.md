# Trade-detail Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `site/trades.html` page (linked from the dashboard) that, per open trade, charts each leg's price and the combined trade return over time (from ~1 month before entry), with a sizing/P&L table — all inline SVG, no dependencies.

**Architecture:** `elp/tradeviz.py` is pure (SVG generator + series reconstruction reusing `elp.trades.idea_return`/`_leg_ret` + per-trade HTML). `tradeviz.py` fetches each leg's daily bars and writes `site/trades.html`. `dashboard.py` gets a link. Network + charts stay out of `dashboard.py`.

**Tech Stack:** Python 3 stdlib only + existing `elp.trades`, `elp.options`, `elp.tiingo`, `elp.express`. No new deps, no JS/CDN.

## Global Constraints

- **stdlib only** — no third-party deps; charts are hand-generated inline SVG (no JS, no CDN).
- **Reuse the engine's math** — combined return via `elp.trades.idea_return`; spread marks via `elp.options.bear_put_spread` (as `_leg_ret` does). Do not reinvent pricing.
- **`idea_return` gotcha:** it evaluates `idea["entry_date"]` eagerly inside `setdefault`, so callers MUST set `idea["entry_date"]` to a `date` first (paper_state rows only carry the ISO string `entry`).
- **Fail soft** — a leg with no/insufficient bars → a note, not a crash; `tradeviz.py` always writes a page and exits 0.
- **Recommendations only / display** — reads `paper_state.json`; changes no engine behavior, no state shape.
- **Grade-C label** — spread PV uses flat IV; the pre-entry dashed line is a hypothetical mark. Both labeled on the page.
- **Offline tests** — synthetic bars/ideas; no network/SMTP in the suite.
- **Reference spec:** `docs/superpowers/specs/2026-07-06-trade-detail-page-design.md`.

---

### Task 1: `elp/tradeviz.py` — inline-SVG line chart

**Files:**
- Create: `elp/tradeviz.py`
- Test: `tests/test_tradeviz.py`

**Interfaces:**
- Produces: `svg_line(series, entry_idx=None, width=640, height=160, pad=24, labels=None) -> str`.
  `series` is a list of dicts `{"pts": [(i, y), ...], "cls": str, "dash": bool}`.

- [ ] **Step 1: Write the failing test** (`tests/test_tradeviz.py`)

```python
"""Offline tests for the trade-detail viz (pure; no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.tradeviz import svg_line  # noqa: E402


class TestSvg(unittest.TestCase):
    def test_line_renders_polyline_and_entry_marker(self):
        svg = svg_line([{"pts": [(0, 1.0), (1, 2.0), (2, 1.5)], "cls": "pv", "dash": False}],
                       entry_idx=1)
        self.assertIn("<svg", svg)
        self.assertIn("<polyline", svg)
        self.assertIn('class="pv"', svg)
        self.assertIn("class=entry", svg)          # vertical entry marker

    def test_dashed_series_has_dasharray(self):
        svg = svg_line([{"pts": [(0, 1.0), (1, 1.1)], "cls": "hyp", "dash": True}])
        self.assertIn("stroke-dasharray", svg)

    def test_empty_is_placeholder(self):
        self.assertIn("no data", svg_line([{"pts": [], "cls": "x", "dash": False}]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tradeviz -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elp.tradeviz'`

- [ ] **Step 3: Write minimal implementation** (`elp/tradeviz.py`)

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tradeviz -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/tradeviz.py tests/test_tradeviz.py
git commit -m "feat(tradeviz): inline-SVG line chart"
```

---

### Task 2: `elp/tradeviz.py` — series reconstruction

**Files:**
- Modify: `elp/tradeviz.py` (append)
- Test: `tests/test_tradeviz.py` (append a class)

**Interfaces:**
- Consumes: `elp.trades.idea_return`/`RISK_FREE`, `elp.options.bear_put_spread`.
- Produces: `combined_series(idea: dict, bars_by_ticker: dict) -> dict`
  (`{"dates", "solid", "dashed", "entry_idx"}`); `leg_price_series(leg: dict, bars: list, entry: date) -> list[tuple[int, float]]`.
  `bars_by_ticker` maps ticker → `[(date, px, vol), ...]`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_tradeviz.py`, before `if __name__`)

```python
from datetime import date  # noqa: E402

from elp.tradeviz import combined_series, leg_price_series  # noqa: E402


def _idea(entry, p_ticker="GILD", n_ticker="VC"):
    return {"supplier": "GILD", "customer": "CAH", "side": 1, "expression": "stock-pair",
            "entry": entry,
            "primary": {"role": "primary", "ticker": p_ticker, "direction": 1, "instrument": "stock",
                        "notional": 200000.0, "entry_px": 100.0},
            "neutralizer": {"role": "neutralizer", "ticker": n_ticker, "direction": -1,
                            "instrument": "stock", "notional": 200000.0, "entry_px": 50.0}}


class TestSeries(unittest.TestCase):
    def test_combined_splits_at_entry_and_matches_idea_return(self):
        # entry on the middle day; GILD rises 90->100->110, VC flat 50
        bars = {"GILD": [(date(2026, 6, 1), 90.0, 1e6), (date(2026, 6, 2), 100.0, 1e6),
                         (date(2026, 6, 3), 110.0, 1e6)],
                "VC": [(date(2026, 6, 1), 50.0, 1e6), (date(2026, 6, 2), 50.0, 1e6),
                       (date(2026, 6, 3), 50.0, 1e6)]}
        cs = combined_series(_idea("2026-06-02"), bars)
        # pre-entry (day 0) is dashed and negative (GILD 90 vs entry ref 100)
        self.assertAlmostEqual(cs["dashed"][0][1], -0.10, places=6)
        self.assertEqual(cs["entry_idx"], 1)
        self.assertAlmostEqual(cs["solid"][-1][1], 0.10, places=6)   # day 2: +10% long leg, VC flat

    def test_leg_price_series_stock_is_prices(self):
        bars = [(date(2026, 6, 1), 90.0, 1e6), (date(2026, 6, 2), 100.0, 1e6)]
        leg = {"ticker": "GILD", "direction": 1, "instrument": "stock", "entry_px": 100.0}
        self.assertEqual(leg_price_series(leg, bars, date(2026, 6, 2)), [(0, 90.0), (1, 100.0)])

    def test_leg_price_series_spread_reprices(self):
        bars = [(date(2026, 6, 1), 100.0, 1e6), (date(2026, 6, 10), 95.0, 1e6)]
        leg = {"ticker": "PG", "direction": -1, "instrument": "spread", "notional": 2e5,
               "entry_px": 100.0, "S0": 100.0, "k_long": 100.0, "k_short": 90.0,
               "T0": 45 / 365.0, "iv": 0.3, "dte": 45}
        s = leg_price_series(leg, bars, date(2026, 6, 1))
        self.assertEqual(len(s), 2)
        self.assertTrue(all(isinstance(y, float) for _, y in s))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tradeviz -v`
Expected: FAIL — `ImportError: cannot import name 'combined_series'`

- [ ] **Step 3: Write minimal implementation** (append to `elp/tradeviz.py`)

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tradeviz -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/tradeviz.py tests/test_tradeviz.py
git commit -m "feat(tradeviz): combined + leg series reconstruction (reuses engine)"
```

---

### Task 3: `elp/tradeviz.py` — per-trade HTML + page CSS

**Files:**
- Modify: `elp/tradeviz.py` (append)
- Test: `tests/test_tradeviz.py` (append a class)

**Interfaces:**
- Consumes: `svg_line`, `combined_series`, `leg_price_series` (Tasks 1-2); `elp.express.describe_leg`.
- Produces: `trade_detail_html(idea: dict, bars_by_ticker: dict) -> str`; `PAGE_CSS: str`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_tradeviz.py`, before `if __name__`)

```python
from elp.tradeviz import PAGE_CSS, trade_detail_html  # noqa: E402


class TestDetailHtml(unittest.TestCase):
    def _bars(self):
        return {"GILD": [(date(2026, 6, 1), 90.0, 1e6), (date(2026, 6, 2), 100.0, 1e6),
                         (date(2026, 6, 3), 110.0, 1e6)],
                "VC": [(date(2026, 6, 1), 50.0, 1e6), (date(2026, 6, 2), 50.0, 1e6),
                       (date(2026, 6, 3), 50.0, 1e6)]}

    def test_block_has_header_charts_and_table(self):
        html = trade_detail_html(_idea("2026-06-02"), self._bars())
        self.assertIn("LONG GILD", html)
        self.assertIn("vs CAH", html)
        self.assertIn("<svg", html)                 # at least one chart
        self.assertIn("combined", html.lower())     # combined section / label
        self.assertIn("Grade-C", html)              # honest caveat

    def test_missing_bars_is_fail_soft(self):
        html = trade_detail_html(_idea("2026-06-02"), {"GILD": [], "VC": []})
        self.assertIn("no price data", html)        # leg note, no crash

    def test_page_css_is_nonempty_string(self):
        self.assertIsInstance(PAGE_CSS, str)
        self.assertIn("svg.chart", PAGE_CSS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tradeviz -v`
Expected: FAIL — `ImportError: cannot import name 'PAGE_CSS'`

- [ ] **Step 3: Write minimal implementation** (append to `elp/tradeviz.py`)

```python
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


def _leg_row(leg: dict, bars: list) -> str:
    latest = f'{bars[-1][1]:.2f}' if bars else "—"
    return (f'<tr><td>{escape(leg["ticker"])}</td>'
            f'<td>{"long" if leg["direction"] > 0 else "short"}</td>'
            f'<td class=sub>{escape(describe_leg(leg))}</td>'
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
                 + _leg_row(p, bars_by_ticker.get(p["ticker"], []))
                 + _leg_row(n, bars_by_ticker.get(n["ticker"], []))
                 + f'<tr><td colspan=5 class=sub>combined: return <b>{last * 100:+.2f}%</b> · '
                   f'P&amp;L <b>{pnl / 1000:+.1f}k</b> on ${p["notional"] / 1000:.0f}k primary notional</td></tr></table>')
    else:
        combined = '<p class=muted>not enough overlapping price history to chart this trade.</p>'
        table = ""

    caveat = ('<p class=muted>Spread marks are Grade-C (flat IV). The pre-entry dashed line is a '
              'hypothetical mark of the fixed structure at earlier dates.</p>')
    return f'<section class=trade>{head}{leg_charts}{combined}{table}{caveat}</section>'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tradeviz -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/tradeviz.py tests/test_tradeviz.py
git commit -m "feat(tradeviz): per-trade HTML block + page CSS"
```

---

### Task 4: `tradeviz.py` entry + pipeline wiring

**Files:**
- Create: `tradeviz.py`
- Modify: `run_paper.sh` (add `tradeviz.py` after `dashboard.py`)
- Test: `tests/test_tradeviz_entry.py`

**Interfaces:**
- Consumes: `elp.tradeviz.trade_detail_html`/`PAGE_CSS`, `elp.tiingo.fetch_daily_bars`.
- Produces: `site/trades.html`. Fail-soft entry.

- [ ] **Step 1: Write the failing test** (`tests/test_tradeviz_entry.py`)

```python
"""Offline test: the tradeviz.py entry writes site/trades.html and fails soft."""
import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tradeviz as entry  # noqa: E402

IDEA = {"supplier": "GILD", "customer": "CAH", "side": 1, "expression": "stock-pair",
        "entry": "2026-06-02",
        "primary": {"role": "primary", "ticker": "GILD", "direction": 1, "instrument": "stock",
                    "notional": 200000.0, "entry_px": 100.0},
        "neutralizer": {"role": "neutralizer", "ticker": "VC", "direction": -1, "instrument": "stock",
                        "notional": 200000.0, "entry_px": 50.0}}
BARS = {"GILD": [(date(2026, 6, 1), 90.0, 1e6), (date(2026, 6, 2), 100.0, 1e6)],
        "VC": [(date(2026, 6, 1), 50.0, 1e6), (date(2026, 6, 2), 50.0, 1e6)]}


class TestEntry(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = os.path.join(os.path.dirname(__file__), "_tvtmp")
        os.makedirs(self._tmp, exist_ok=True)
        os.chdir(self._tmp)
        entry.fetch_daily_bars = lambda t, start=None: BARS.get(t, [])

    def tearDown(self):
        import shutil
        entry.fetch_daily_bars = _ORIG
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_writes_trades_html(self):
        json.dump({"open": [IDEA]}, open("paper_state.json", "w"))
        entry.build()
        self.assertTrue(os.path.exists("site/trades.html"))
        self.assertIn("LONG GILD", open("site/trades.html").read())

    def test_no_state_still_writes_page(self):
        entry.build()                                 # no paper_state.json -> fail soft
        self.assertTrue(os.path.exists("site/trades.html"))
        self.assertIn("No open trades", open("site/trades.html").read())

    def test_fetch_error_is_fail_soft(self):
        json.dump({"open": [IDEA]}, open("paper_state.json", "w"))
        def boom(t, start=None): raise RuntimeError("net down")
        entry.fetch_daily_bars = boom
        entry.build()                                 # must not raise
        self.assertTrue(os.path.exists("site/trades.html"))


_ORIG = entry.fetch_daily_bars


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tradeviz_entry -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradeviz'`

- [ ] **Step 3: Write minimal implementation** (`tradeviz.py`)

```python
"""Build site/trades.html: per-open-trade leg + combined charts over time. Fetches each leg's daily
bars (~35 days before entry) from Tiingo. Fail-soft. Run: python3 tradeviz.py
"""
import json
import os
from datetime import date, timedelta

from elp.tiingo import fetch_daily_bars
from elp.tradeviz import PAGE_CSS, trade_detail_html

STATE, OUT = "paper_state.json", "site/trades.html"


def _bars_for(idea: dict) -> dict:
    out = {}
    try:
        start = (date.fromisoformat(idea["entry"]) - timedelta(days=35)).isoformat()
    except (ValueError, KeyError):
        start = "2015-01-01"
    for leg in (idea["primary"], idea["neutralizer"]):
        t = leg["ticker"]
        if t not in out:
            try:
                out[t] = fetch_daily_bars(t, start=start)
            except Exception:
                out[t] = []
    return out


def build() -> None:
    try:
        state = json.load(open(STATE))
    except FileNotFoundError:
        state = {"open": []}
    blocks = ""
    for idea in state.get("open", []):
        try:
            blocks += trade_detail_html(idea, _bars_for(idea))
        except Exception as e:                        # one bad trade never kills the page
            blocks += (f'<section class=trade><p class=muted>{idea.get("supplier", "?")}: '
                       f'chart error ({type(e).__name__})</p></section>')
    if not blocks:
        blocks = '<p class=muted>No open trades.</p>'
    doc = (f'<!doctype html><html><head><meta charset=utf-8><title>Trade details</title>'
           f'<style>{PAGE_CSS}</style></head><body><h1>Trade details</h1>'
           f'<p class=sub><a href="index.html">← dashboard</a></p>{blocks}</body></html>')
    os.makedirs("site", exist_ok=True)
    open(OUT, "w").write(doc)
    print(f"wrote {OUT} ({len(state.get('open', []))} trades)")


if __name__ == "__main__":
    build()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tradeviz_entry -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire the pipeline**

Edit `run_paper.sh` — add the tradeviz line right after `dashboard.py`:

```bash
python3 dashboard.py >> paper_run.log 2>&1
python3 tradeviz.py  >> paper_run.log 2>&1   # per-trade detail page -> site/trades.html (fails soft)
```

(`site/` is already gitignored, so `trades.html` needs no new ignore rule.)

- [ ] **Step 6: Commit**

```bash
git add tradeviz.py tests/test_tradeviz_entry.py run_paper.sh
git commit -m "feat(tradeviz): entry writes site/trades.html + pipeline wiring"
```

---

### Task 5: Dashboard link to the detail page

**Files:**
- Modify: `dashboard.py` (add a `Trade details →` link in the header)
- Test: `tests/test_dashboard.py` (add a build() integration test)

**Interfaces:**
- Consumes: nothing new (static link).

- [ ] **Step 1: Write the failing test** (add to `tests/test_dashboard.py`, before `if __name__` if present, else at end)

```python
class TestDashboardLink(unittest.TestCase):
    def test_index_links_to_trades_page(self):
        import dashboard, json, os, shutil
        cwd = os.getcwd(); tmp = os.path.join(os.path.dirname(__file__), "_dashtmp")
        os.makedirs(tmp, exist_ok=True); os.chdir(tmp)
        try:
            json.dump({"generated_utc": "t", "start": "2026-07-04", "open": [], "closed": [],
                       "stats": {}}, open("paper_state.json", "w"))
            dashboard.build()
            self.assertIn("trades.html", open("site/index.html").read())
        finally:
            os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard -v`
Expected: FAIL — `AssertionError: 'trades.html' not found`

- [ ] **Step 3: Implement** (edit `dashboard.py`)

In the doc template, add a link line right after the `<p class=sub>generated ...</p>` header line. Change:

```python
<p class=sub>generated {escape(str(s['generated_utc']))} · paper start {escape(str(s['start']))} · recommendations only, no execution</p>
```

to:

```python
<p class=sub>generated {escape(str(s['generated_utc']))} · paper start {escape(str(s['start']))} · recommendations only, no execution</p>
<p class=sub><a href="trades.html">Trade details (per-trade charts) →</a></p>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_dashboard -v` then the full suite `python3 -m unittest discover -s tests`.
Expected: PASS; full suite OK.

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): link to the trade-detail page"
```

---

## Verification (whole feature)

1. **Full offline suite:** `python3 -m unittest discover -s tests` → OK.
2. **Live build (needs Tiingo token; a few price fetches per leg):** `python3 track.py` then `python3 tradeviz.py` → prints `wrote site/trades.html (N trades)`; open `site/trades.html` and confirm each open trade shows leg chart(s), a combined solid+dashed return chart with the red entry marker, and the sizing/P&L table. `python3 dashboard.py` → `site/index.html` has the `Trade details →` link.
3. **Fail-soft:** temporarily rename `.tiingo_token`, run `python3 tradeviz.py` → still writes `site/trades.html` (charts replaced by "no price data" notes), exits 0. Restore.

## Self-Review

**Spec coverage:** §2 architecture → Tasks 1-5. §3 series reconstruction (reuse idea_return/_leg_ret; solid/dashed split; spread mark) → Task 2. §4 SVG → Task 1. §5 page layout (header/leg charts/combined/table/caveat) → Task 3; page + link → Tasks 4-5. §6 testing → tests in every task. §7 out-of-scope honored (no JS, open trades only, Grade-C label, no engine change).

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `svg_line(series=[{"pts","cls","dash"}], entry_idx, labels)` (Task 1) is called with exactly that shape by `trade_detail_html` (Task 3). `combined_series` returns `{"dates","solid","dashed","entry_idx"}` consumed by `trade_detail_html`. `leg_price_series(leg, bars, entry)` returns `[(i, y)]` fed into `svg_line`'s `pts`. `trade_detail_html(idea, bars_by_ticker)` / `PAGE_CSS` consumed by `tradeviz.build` (Task 4). `combined_series` sets `idea["entry_date"]` before `idea_return` (the documented gotcha).

## Out of scope
- Interactive/JS charts; closed-trade pages; a precise two-leg option cost/greeks model; any engine or state-shape change.
