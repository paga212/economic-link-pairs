"""Monthly adjusted-close prices (Yahoo Finance, keyless) and returns — Phase 0 only.

Yahoo is unofficial and survivorship-biased (delisted names disappear); it is fine
for validating signal *direction* on still-listed pairs but is NOT the production
source. Production uses Tiingo with an API key (see research/08-data-procurement.md).
Pure stdlib: no pandas, no third-party HTTP.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timezone

_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1mo"


def fetch_monthly(symbol: str, years: int = 15) -> list[tuple[date, float]]:
    """Monthly (first-of-month date, adjusted close) series, oldest first."""
    url = _CHART.format(sym=symbol, rng=f"{years}y")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    out: list[tuple[date, float]] = []
    for t, p in zip(ts, adj):
        if p is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date()
        out.append((date(d.year, d.month, 1), float(p)))
    return out


def monthly_returns(series: list[tuple[date, float]]) -> dict[tuple[int, int], float]:
    """{(year, month): simple monthly return} from an adjusted-close series."""
    rets: dict[tuple[int, int], float] = {}
    for (_d0, p0), (d1, p1) in zip(series, series[1:]):
        if p0:
            rets[(d1.year, d1.month)] = p1 / p0 - 1.0
    return rets
