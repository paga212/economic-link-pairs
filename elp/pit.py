"""Point-in-time link table: which links a trader could have known in each formation month.

SEC filings carry a `filed` date, so a disclosed customer link has an exact public birth date.
A link is usable from the month AFTER it was filed (you cannot trade on a filing during the
month it lands, without knowing the day) and lapses LIFE_MONTHS later.

LIFE_MONTHS = 15, not 12: annual filings arrive roughly every 12 months, and a 12-month life
opens a hole whenever a filing slips. 15 bridges a slip without letting a link survive a fully
missed cycle. This is the module's only judgement call. Pure stdlib.
"""
from __future__ import annotations

from datetime import date

LIFE_MONTHS = 15


def _idx(ym: tuple[int, int]) -> int:
    """Months since year 0, so month arithmetic and comparison are plain integers."""
    return ym[0] * 12 + (ym[1] - 1)


def links_asof(dated: list[dict], months: list[tuple[int, int]],
               life: int = LIFE_MONTHS) -> dict[tuple[int, int], list[tuple[str, str]]]:
    """{formation month: sorted unique [(supplier, customer)] live that month}."""
    spans = []
    for r in dated:
        f = date.fromisoformat(r["filed"])
        born = _idx((f.year, f.month))                  # live from born+1 .. born+life
        spans.append((born, r["supplier"], r["customer"]))
    out = {}
    for ym in months:
        i = _idx(ym)
        out[ym] = sorted({(s, c) for born, s, c in spans if born < i <= born + life})
    return out
