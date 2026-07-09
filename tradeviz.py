"""Build site/trades.html: per-open-trade leg + combined charts over time. Fetches each leg's daily
bars (~35 days before entry) from Tiingo. Fail-soft. Run: python3 tradeviz.py
"""
import json
import os
from datetime import date, timedelta

from elp.tiingo import fetch_daily_ohlc
from elp.tradeviz import PAGE_CSS, THEME_BUTTON, THEME_INIT, trade_detail_html

STATE, OUT = "paper_state.json", "site/trades.html"


def _bars_for(idea: dict):
    """(close_bars, ohlc_bars) dicts per leg ticker. One OHLC fetch each; close bars derived
    from it (so the return/spread math and candlesticks share a single request)."""
    ohlc = {}
    try:
        start = (date.fromisoformat(idea["entry"]) - timedelta(days=35)).isoformat()
    except (ValueError, KeyError):
        start = "2015-01-01"
    for leg in (idea["primary"], idea["neutralizer"]):
        t = leg["ticker"]
        if t not in ohlc:
            try:
                ohlc[t] = fetch_daily_ohlc(t, start=start)
            except Exception as e:      # fail-soft, but never silently: an empty series here is
                                        # a fetch failure, not an absence of price history
                print(f"  warn {t}: price fetch failed ({type(e).__name__}); chart degraded")
                ohlc[t] = []
    close = {t: [(d, c, v) for d, _o, _h, _l, c, v in bars] for t, bars in ohlc.items()}
    return close, ohlc


def build() -> None:
    try:
        state = json.load(open(STATE))
    except (FileNotFoundError, ValueError):
        state = {"open": []}
    blocks = ""
    for idea in state.get("open", []):
        try:
            close_bars, ohlc_bars = _bars_for(idea)
            blocks += trade_detail_html(idea, close_bars, ohlc_bars)
        except Exception as e:                        # one bad trade never kills the page
            blocks += (f'<section class=trade><p class=muted>{idea.get("supplier", "?")}: '
                       f'chart error ({type(e).__name__})</p></section>')
    if not blocks:
        blocks = '<p class=muted>No open trades.</p>'
    doc = (f'<!doctype html><html><head><meta charset=utf-8><title>Trade details</title>'
           f'<style>{PAGE_CSS}</style>{THEME_INIT}</head><body>{THEME_BUTTON}<h1>Trade details</h1>'
           f'<p class=sub><a href="index.html">← dashboard</a></p>{blocks}</body></html>')
    os.makedirs("site", exist_ok=True)
    open(OUT, "w").write(doc)
    print(f"wrote {OUT} ({len(state.get('open', []))} trades)")


if __name__ == "__main__":
    build()
