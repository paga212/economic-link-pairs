"""Phase B: LLM-extracted customer-supplier links from EDGAR (diversify the universe).

Discovery via EDGAR full-text search -> for each currently-listed supplier, LLM-extract the
disclosed major customers (with a named flag + confidence) from the concentration passages
-> resolve both legs to tickers -> write data/llm_links.json. Bounded sample; Haiku (cheap).
The goal is BREADTH of customers (vs the Apple-heavy hand set), measured here.

Run: python3 phase_b_build.py [max_filers]
"""
import json
import sys

from elp.edgar import (concentration_snippets, filing_text, full_text_search,
                       latest_10k, load_ticker_map, resolve)
from elp.llm import extract_json

PHRASES = ["accounted for approximately", "of our net revenue", "of net sales", "largest customer"]

# NB: contains literal JSON braces -> concatenate the excerpt, never str.format this.
PROMPT = (
    "From this 10-K excerpt, extract each MAJOR CUSTOMER the company discloses (a customer "
    "that is material / >=10% of sales, or a named significant customer). Return ONLY a JSON "
    'array; each item: {"customer": "<company name as written>", "pct": <number or null>, '
    '"named": <true if the customer is actually named, false if only "one customer"/"a '
    'customer">, "confidence": <0..1>}. Empty array if none.\n\nExcerpt:\n')


def main(max_filers: int = 25) -> None:
    by_cik, by_name = load_ticker_map()
    seen, links = set(), []
    scanned = 0
    for phrase in PHRASES:
        if scanned >= max_filers:
            break
        try:
            hits = full_text_search(phrase, forms="10-K")
        except Exception:
            continue
        for h in hits:
            if scanned >= max_filers or not h["cik"] or h["cik"] in seen:
                continue
            seen.add(h["cik"])
            supp = by_cik.get(h["cik"], {}).get("ticker")
            if not supp:                       # only currently-listed (tradeable) suppliers
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

    uniq = {(x["supplier"], x["customer"]): x for x in links}
    out = list(uniq.values())
    json.dump(out, open("data/llm_links.json", "w"), indent=1)
    named = sum(1 for x in out if x.get("named"))
    print(f"\nscanned {scanned} listed filers | resolved links {len(out)} | named {named} "
          f"| distinct customers {len({x['customer'] for x in out})} "
          f"| distinct suppliers {len({x['supplier'] for x in out})}")
    for x in sorted(out, key=lambda z: z["supplier"])[:24]:
        print(f"  {x['supplier']:5} -> {x['customer']:5}  pct={x['pct']} named={x['named']} "
              f"conf={x['confidence']}  ({x['customer_raw']!r})")
    print("\n-> data/llm_links.json (gitignored)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 25)
