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
    raw = os.environ.get("TIINGO_API_KEY")
    if not raw:
        for path in (_TOKEN_FILE, os.path.expanduser("~/.tiingo_token")):
            if os.path.exists(path):
                raw = open(path).read()
                break
    if not raw:
        raise RuntimeError(
            "No Tiingo token found. Set TIINGO_API_KEY or create .tiingo_token "
            "(see README / research/08).")
    tok = raw.strip()
    if "=" in tok:  # tolerate a pasted `export TIINGO_API_KEY='...'` line, not just the raw token
        tok = tok.split("=", 1)[1]
    return tok.strip().strip("'").strip('"').strip()


def _fetch(url: str, symbol: str) -> list:
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "Authorization": f"Token {_token()}",  # token in header, not URL
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Tiingo HTTP {e.code} for {symbol}") from None  # never surface the token


def fetch_monthly(symbol: str, start: str = "1995-01-01") -> list[tuple[date, float]]:
    """Monthly (first-of-month date, adjusted close) series, oldest first."""
    rows = _fetch(_URL.format(sym=symbol.lower(), start=start), symbol)
    out: list[tuple[date, float]] = []
    for row in rows:
        d = datetime.fromisoformat(row["date"].replace("Z", "")).date()
        out.append((date(d.year, d.month, 1), float(row["adjClose"])))
    return out


def fetch_daily(symbol: str, start: str = "2015-01-01") -> list[tuple[date, float]]:
    """Daily (date, adjusted close) series, oldest first (for the per-trade engine)."""
    url = (f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?startDate={start}")
    out: list[tuple[date, float]] = []
    for row in _fetch(url, symbol):
        d = datetime.fromisoformat(row["date"].replace("Z", "")).date()
        out.append((d, float(row["adjClose"])))
    return out
