"""Tiingo EOD monthly prices — the production price source (replaces the Yahoo prototype).

Reads the API token from the TIINGO_API_KEY env var or a gitignored .tiingo_token file,
and sends it as an Authorization header (never in a URL, never printed). Returns the
same (first-of-month date, adjusted close) shape as elp.prices, so the backtest engine
is source-agnostic. Pure stdlib.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime

_TOKEN_FILE = ".tiingo_token"
_URL = ("https://api.tiingo.com/tiingo/daily/{sym}/prices"
        "?startDate={start}&resampleFreq=monthly")


def _token() -> str:
    tok = os.environ.get("TIINGO_API_KEY")
    if not tok:
        for path in (_TOKEN_FILE, os.path.expanduser("~/.tiingo_token")):
            if os.path.exists(path):
                tok = open(path).read().strip()
                break
    if not tok:
        raise RuntimeError(
            "No Tiingo token found. Set TIINGO_API_KEY or create .tiingo_token "
            "(see README / research/08).")
    return tok


def fetch_monthly(symbol: str, start: str = "1995-01-01") -> list[tuple[date, float]]:
    """Monthly (first-of-month date, adjusted close) series, oldest first."""
    url = _URL.format(sym=symbol.lower(), start=start)
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "Authorization": f"Token {_token()}",  # token in header, not URL
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            rows = json.load(resp)
    except urllib.error.HTTPError as e:
        # never surface the token; re-raise with just the status
        raise RuntimeError(f"Tiingo HTTP {e.code} for {symbol}") from None
    out: list[tuple[date, float]] = []
    for row in rows:
        d = datetime.fromisoformat(row["date"].replace("Z", "")).date()
        out.append((date(d.year, d.month, 1), float(row["adjClose"])))
    return out
