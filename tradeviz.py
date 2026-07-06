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
    except (FileNotFoundError, ValueError):
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
