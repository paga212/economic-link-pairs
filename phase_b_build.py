"""Phase B: build the diversified customer-supplier universe via LLM extraction from EDGAR.

Paginated discovery -> for each currently-listed supplier, LLM-extract disclosed major
customers (named flag + confidence) from the concentration passages -> resolve both legs to
tickers -> write universe_links.json (committed; the tracker reads it via links.load_universe).
Haiku (cheap). Run periodically to refresh; the daily tracker does NOT re-extract.

Run: python3 phase_b_build.py [max_filers]
"""
import json
import sys

from elp.edgar import (concentration_snippets, filing_text, full_text_search,
                       latest_10k, load_ticker_map, resolve)
from elp.llm import extract_json

PHRASES = ["accounted for approximately", "of our net revenue", "of net sales",
           "largest customer", "of our total revenue", "significant customers"]

# NB: contains literal JSON braces -> concatenate the excerpt, never str.format this.
PROMPT = (
    "From this 10-K excerpt, extract each MAJOR CUSTOMER the company discloses (a customer "
    "that is material / >=10% of sales, or a named significant customer). Return ONLY a JSON "
    'array; each item: {"customer": "<company name as written>", "pct": <number or null>, '
    '"named": <true if the customer is actually named, false if only "one customer"/"a '
    'customer">, "confidence": <0..1>}. Empty array if none.\n\nExcerpt:\n')

OUT = "universe_links.json"


def main(max_filers: int = 150) -> None:
    by_cik, by_name = load_ticker_map()
    seen, links = set(), []
    scanned = 0
    for phrase in PHRASES:
        for frm in range(0, 300, 10):          # paginate the full-text search
            if scanned >= max_filers:
                break
            try:
                hits = full_text_search(phrase, forms="10-K", frm=frm)
            except Exception:
                break
            if not hits:
                break
            for h in hits:
                if scanned >= max_filers or not h["cik"] or h["cik"] in seen:
                    continue
                seen.add(h["cik"])
                supp = by_cik.get(h["cik"], {}).get("ticker")
                if not supp:                    # only currently-listed suppliers
                    continue
                f = latest_10k(h["cik"])
                if not f:
                    continue
                acc, doc, dt = f
                try:
                    snips = concentration_snippets(filing_text(h["cik"], acc, doc))
                except Exception:
                    continue
                if not snips:
                    continue
                scanned += 1
                try:
                    items = extract_json(PROMPT + "\n...\n".join(snips)) or []
                except Exception as e:
                    print(f"  llm err {supp}: {type(e).__name__}")
                    continue
                for it in items if isinstance(items, list) else []:
                    cust = resolve(str(it.get("customer", "")), by_name)
                    if cust and supp != cust:
                        links.append({"supplier": supp, "customer": cust, "pct": it.get("pct"),
                                      "named": it.get("named"), "confidence": it.get("confidence"),
                                      "customer_raw": it.get("customer"), "date": dt})
                if scanned % 20 == 0:
                    print(f"  ...scanned {scanned}, links so far {len(links)}")
        if scanned >= max_filers:
            break

    uniq = {(x["supplier"], x["customer"]): x for x in links}
    out = sorted(uniq.values(), key=lambda z: z["supplier"])
    json.dump(out, open(OUT, "w"), indent=1)
    named = [x for x in out if x.get("named") and (x.get("confidence") or 0) >= 0.6]
    print(f"\nscanned {scanned} listed filers | resolved links {len(out)} "
          f"| named+confident {len(named)} | distinct customers {len({x['customer'] for x in named})} "
          f"| distinct suppliers {len({x['supplier'] for x in named})}")
    from collections import Counter
    print("top customers:", Counter(x["customer"] for x in named).most_common(10))
    print(f"-> {OUT} (committed universe; tracker reads via links.load_universe)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
