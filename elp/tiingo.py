"""Tiingo EOD monthly prices — the production price source (replaces the Yahoo prototype).

Reads the API token from the TIINGO_API_KEY env var or a gitignored .tiingo_token file,
and sends it as an Authorization header (never in a URL, never printed). Returns the
same (first-of-month date, adjusted close) shape as elp.prices, so the backtest engine
is source-agnostic. Pure stdlib.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime

_TOKEN_FILE = ".tiingo_token"
_URL = ("https://api.tiingo.com/tiingo/daily/{sym}/prices"
        "?startDate={start}&resampleFreq=monthly")

# A single transient failure used to be swallowed by callers into an empty series, which then
# rendered as a *data* claim ("no price data") rather than a fetch error. Retry the transient
# classes only; a 4xx is our bug (bad symbol, bad token) and must surface immediately.
_RETRIES, _BACKOFF_S = 3, 1.0


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
    for attempt in range(1, _RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == _RETRIES:
                raise RuntimeError(f"Tiingo HTTP {e.code} for {symbol}") from None  # no token
        except (urllib.error.URLError, TimeoutError):     # DNS, reset, read timeout
            if attempt == _RETRIES:
                raise
        time.sleep(_BACKOFF_S * attempt)


def _parse_bars(rows: list) -> list[tuple[date, float, float]]:
    """(date, adjusted close, adjusted volume) oldest-first; tolerates missing adjVolume."""
    out: list[tuple[date, float, float]] = []
    for row in rows:
        d = datetime.fromisoformat(row["date"].replace("Z", "")).date()
        vol = row.get("adjVolume", row.get("volume", 0.0))
        out.append((d, float(row["adjClose"]), float(vol or 0.0)))
    return out


def fetch_monthly(symbol: str, start: str = "1995-01-01") -> list[tuple[date, float]]:
    """Monthly (first-of-month date, adjusted close) series, oldest first."""
    rows = _fetch(_URL.format(sym=symbol.lower(), start=start), symbol)
    out: list[tuple[date, float]] = []
    for row in rows:
        d = datetime.fromisoformat(row["date"].replace("Z", "")).date()
        out.append((date(d.year, d.month, 1), float(row["adjClose"])))
    return out


def fetch_daily_bars(symbol: str, start: str = "2015-01-01") -> list[tuple[date, float, float]]:
    """Daily (date, adjusted close, adjusted volume) series, oldest first."""
    url = f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?startDate={start}"
    return _parse_bars(_fetch(url, symbol))


def fetch_daily(symbol: str, start: str = "2015-01-01") -> list[tuple[date, float]]:
    """Daily (date, adjusted close) series, oldest first (for the per-trade engine)."""
    return [(d, px) for d, px, _ in fetch_daily_bars(symbol, start)]


def fetch_daily_ohlc(symbol: str, start: str = "2015-01-01") -> list[tuple]:
    """Daily (date, adjOpen, adjHigh, adjLow, adjClose, adjVolume) series, oldest first — for
    candlestick charts. Falls back to raw o/h/l/c if an adjusted field is absent."""
    url = f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?startDate={start}"
    out: list[tuple] = []
    for r in _fetch(url, symbol):
        d = datetime.fromisoformat(r["date"].replace("Z", "")).date()
        o = r.get("adjOpen", r.get("open"))
        h = r.get("adjHigh", r.get("high"))
        low = r.get("adjLow", r.get("low"))
        c = r.get("adjClose", r.get("close"))
        vol = r.get("adjVolume", r.get("volume", 0.0))
        if None in (o, h, low, c):        # incomplete bar -> skip (candles need full OHLC)
            continue
        out.append((d, float(o), float(h), float(low), float(c), float(vol or 0.0)))
    return out


_FUND = "https://api.tiingo.com/tiingo/fundamentals/{sym}/{kind}"


def fetch_marketcap(ticker: str) -> float | None:
    """Latest non-zero marketCap from Tiingo fundamentals daily. None on any error/empty."""
    try:
        rows = _fetch(_FUND.format(sym=ticker.lower(), kind="daily"), ticker)
        for r in reversed(rows):
            mc = r.get("marketCap")
            if mc:
                return float(mc)
    except Exception:
        return None
    return None


def fetch_statement_dates(ticker: str) -> list[str]:
    """Sorted unique fiscal period-end dates (YYYY-MM-DD) from Tiingo statements. [] on error."""
    try:
        rows = _fetch(_FUND.format(sym=ticker.lower(), kind="statements"), ticker)
        return sorted({r["date"][:10] for r in rows if r.get("date")})
    except Exception:
        return []
