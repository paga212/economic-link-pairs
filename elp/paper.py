"""Paper-trade log loading + scoring, shared by score.py and dashboard.py."""
from __future__ import annotations

import json

from elp.prices import monthly_returns
from elp.tiingo import fetch_monthly

LOG = "paper_log.jsonl"


def load_entries(path: str = LOG) -> list[dict]:
    try:
        return [json.loads(x) for x in open(path) if x.strip()]
    except FileNotFoundError:
        return []


def fetch_returns(entries: list[dict]) -> dict:
    tickers = {s for e in entries for s, _ in e["longs"] + e["shorts"]}
    out = {}
    for t in sorted(tickers):
        try:
            out[t] = monthly_returns(fetch_monthly(t, start="2015-01-01"))
        except Exception:
            pass
    return out


def _leg(names, hk, returns):
    vals = [returns[s].get(hk) for s, _ in names if returns.get(s, {}).get(hk) is not None]
    return sum(vals) / len(vals) if vals else None


def score(entries: list[dict], returns: dict) -> tuple[list[dict], dict]:
    """(matured rows, totals). Each row: {holding, long, short, ls}. Gross (no costs yet)."""
    rows, cum, wins = [], 0.0, 0
    for e in entries:
        hk = tuple(e["holding"])
        lr, sr = _leg(e["longs"], hk, returns), _leg(e["shorts"], hk, returns)
        if lr is None or sr is None:
            continue  # holding month not complete / prices missing
        ls = lr - sr
        cum += ls
        wins += ls > 0
        rows.append({"holding": hk, "long": lr, "short": sr, "ls": ls})
    n = len(rows)
    totals = {"n": n, "cum": cum, "avg": (cum / n if n else 0.0), "hit": (wins / n if n else 0.0)}
    return rows, totals
