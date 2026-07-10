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


def main(start: str = "2013q1", end: str = "2025q4", out: str = OUT) -> None:
    by_cik, by_name = load_ticker_map()
    titles = title_index(by_cik)
    resolved: dict[str, str | None] = {}  # per-run memo: resolve_member() is called ~6,300x/quarter
    seen, links = set(), []
    for q in quarters(start, end):
        path = os.path.join(tempfile.gettempdir(), f"fsds_{q}.zip")
        try:
            fetch_quarter(q, path)
            rows = major_customers(path)
        except Exception as e:
            print(f"  warn {q}: {type(e).__name__} — quarter skipped")
            continue
        finally:
            if os.path.exists(path):
                os.remove(path)
        added = 0
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
            key = (supplier, customer, r["filed"].isoformat())
            if key in seen:
                continue
            seen.add(key)
            links.append({"supplier": supplier, "customer": customer,
                          "filed": r["filed"].isoformat()})
            added += 1
        print(f"{q}: {len(rows):>6} tagged rows | +{added:>4} links | "
              f"total {len(links):>5} | suppliers {len({x['supplier'] for x in links}):>4}")
    links.sort(key=lambda x: (x["filed"], x["supplier"], x["customer"]))
    json.dump(links, open(out, "w"), indent=1)
    print(f"\nwrote {out}: {len(links)} links, "
          f"{len({x['supplier'] for x in links})} suppliers, "
          f"{len({x['customer'] for x in links})} customers")


if __name__ == "__main__":
    main(*sys.argv[1:3])
