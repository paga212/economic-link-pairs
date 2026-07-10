"""Build the point-in-time customer-supplier link universe from SEC XBRL. No LLM.

Streams each quarterly Financial Statement Data Set, keeps facts tagged on
srt:MajorCustomersAxis, resolves the filer CIK to a supplier ticker and the member string to a
customer ticker, and writes dated links to xbrl_links.json. `filed` is the date the disclosure
became public, so the links are point-in-time by construction.

Zips are ~95-125MB each and are deleted after parsing. Run: python3 xbrl_build.py [start] [end]
"""
import json
import os
import sys
import tempfile

from elp.edgar import load_ticker_map, resolve_member, title_index
from elp.fsds import fetch_quarter, major_customers, quarters

OUT = "xbrl_links.json"


def _principal(rows_in_group: list[tuple[str, float | None, str, str]]) -> tuple[str, bool]:
    """Pick the ONE principal customer for a (supplier, filed) group.

    Rankable path: sum the disclosed USD revenue per customer (a filing can tag a
    customer's revenue more than once, e.g. across contexts within the same fact
    group; summing captures the customer's total attributed revenue rather than an
    arbitrary single line -- and is a no-op when there's only one line) and take the
    customer with the largest total. A tag counts as revenue only if its name STARTS
    WITH "revenue" (case-insensitive) -- a plain substring check would also match
    e.g. "CostOfRevenue", which is a cost figure, not customer revenue, and must not
    be used for ranking.

    Fallback path: if no row in the group is a USD revenue row, fall back to the
    alphabetically-first customer so the group is still emitted, not silently dropped.

    Returns (customer, used_fallback).
    """
    totals: dict[str, float] = {}
    for customer, value, tag, uom in rows_in_group:
        if uom == "USD" and tag.lower().startswith("revenue") and value is not None:
            totals[customer] = totals.get(customer, 0.0) + value
    if totals:
        return max(totals, key=totals.get), False
    return min(customer for customer, _, _, _ in rows_in_group), True


def main(start: str = "2013q1", end: str = "2025q4", out: str = OUT) -> None:
    by_cik, by_name = load_ticker_map()
    titles = title_index(by_cik)
    resolved: dict[str, str | None] = {}  # per-run memo: resolve_member() is called ~6,300x/quarter
    seen, links = set(), []
    all_quarters = quarters(start, end)
    skipped: list[str] = []
    rankable, fallback = 0, 0
    for q in all_quarters:
        path = os.path.join(tempfile.gettempdir(), f"fsds_{os.getpid()}_{q}.zip")
        try:
            fetch_quarter(q, path)
            rows = major_customers(path)
        except Exception as e:
            print(f"  warn {q}: {type(e).__name__} — quarter skipped")
            skipped.append(q)
            continue
        finally:
            if os.path.exists(path):
                os.remove(path)
        # Group resolved, non-self rows by (supplier, filed) so each filing's disclosed
        # customers can be ranked against each other -- a filing's principal customer is
        # the one with the largest disclosed revenue, not the alphabetically-first ticker.
        groups: dict[tuple[str, str], list[tuple[str, float | None, str, str]]] = {}
        for r in rows:
            supplier = by_cik.get(r["cik"], {}).get("ticker")
            if not supplier:
                continue
            member = r["member"]
            if member not in resolved:
                resolved[member] = resolve_member(member, by_name, titles)
            customer = resolved[member]
            if not customer or customer == supplier:
                continue
            groups.setdefault((supplier, r["filed"]), []).append(
                (customer, r["value"], r["tag"], r["uom"]))
        added = 0
        for (supplier, filed), rows_in_group in groups.items():
            customer, used_fallback = _principal(rows_in_group)
            fallback += used_fallback
            rankable += not used_fallback
            key = (supplier, customer, filed.isoformat())
            if key in seen:
                continue
            seen.add(key)
            links.append({"supplier": supplier, "customer": customer, "filed": filed.isoformat()})
            added += 1
        print(f"{q}: {len(rows):>6} tagged rows | +{added:>4} links | "
              f"total {len(links):>5} | suppliers {len({x['supplier'] for x in links}):>4}")
    links.sort(key=lambda x: (x["filed"], x["supplier"], x["customer"]))
    json.dump(links, open(out, "w"), indent=1)
    parsed = len(all_quarters) - len(skipped)
    print(f"\ncoverage: {parsed}/{len(all_quarters)} quarters parsed, {len(skipped)} skipped")
    if skipped:
        print(f"  SKIPPED: {', '.join(skipped)}")
    print(f"principal-customer selection: {rankable} rankable (by USD revenue), "
          f"{fallback} fallback (alphabetical, no rankable rows)")
    print(f"wrote {out}: {len(links)} links, "
          f"{len({x['supplier'] for x in links})} suppliers, "
          f"{len({x['customer'] for x in links})} customers")


if __name__ == "__main__":
    main(*sys.argv[1:3])
