"""Point-in-time link table: which links a trader could have known in each formation month.

SEC filings carry a `filed` date, so a disclosed customer link has an exact public birth date.
A link is usable from the month AFTER it was filed (you cannot trade on a filing during the
month it lands, without knowing the day) and lapses LIFE_MONTHS later.

LIFE_MONTHS = 15, not 12: annual filings arrive roughly every 12 months, and a 12-month life
opens a hole whenever a filing slips. 15 bridges a slip without letting a link survive a fully
missed cycle. This is the module's only judgement call.

SUPERSESSION: 10-Qs file quarterly against a ~12-month refiling cadence, so a supplier's
successive filings routinely overlap -- more than one of its links can be "live" in the same
month. Only one can be the principal customer, so `links_asof` keeps at most one link per
supplier per month: the one from that supplier's MOST RECENT `filed` date among its live
links. A newer disclosure supersedes an older, still-live one. Ties on `filed` (same supplier,
same day, different customers) fall back to the alphabetically-first customer; this should be
vanishingly rare since xbrl_build.py emits one customer per (supplier, filed). Pure stdlib.
"""
from __future__ import annotations

from datetime import date

LIFE_MONTHS = 15


def _idx(ym: tuple[int, int]) -> int:
    """Months since year 0, so month arithmetic and comparison are plain integers."""
    return ym[0] * 12 + (ym[1] - 1)


def links_asof(dated: list[dict], months: list[tuple[int, int]],
               life: int = LIFE_MONTHS) -> dict[tuple[int, int], list[tuple[str, str]]]:
    """{formation month: sorted [(supplier, customer)] live that month, at most one per
    supplier -- the most-recently-filed live link. See module docstring for the rule."""
    spans = []
    for r in dated:
        f = date.fromisoformat(r["filed"])
        born = _idx((f.year, f.month))                  # live from born+1 .. born+life
        spans.append((born, f, r["supplier"], r["customer"]))
    out = {}
    for ym in months:
        i = _idx(ym)
        best: dict[str, tuple] = {}                      # supplier -> (filed, customer)
        for born, f, s, c in spans:
            if not (born < i <= born + life):
                continue
            cur = best.get(s)
            if cur is None or f > cur[0] or (f == cur[0] and c < cur[1]):
                best[s] = (f, c)
        out[ym] = sorted((s, c) for s, (f, c) in best.items())
    return out
