"""Phase 2a build: sample EDGAR for NAMED+QUANTIFIED customer links; measure yield.

Autonomous default (user away): 'named + quantified only' link sourcing — no
inference, no LLM/key. This estimates how large that named-only universe is (the
key viability question) on a bounded sample, writes candidate links to
data/named_links.csv (gitignored), and prints yield stats. Ticker resolution of
BOTH legs is the precision filter — unresolvable names are dropped.

Run: python3 phase2a_build.py [max_filings]
"""
import csv
import sys

from elp.edgar import (extract_disclosures, filing_text, full_text_search,
                       latest_10k, load_ticker_map, norm, resolve)

PHRASES = ["accounted for approximately", "of our net revenue",
           "represented approximately", "of our total revenue"]


def main(max_filings: int = 30) -> None:
    by_cik, by_name = load_ticker_map()
    seen, links = set(), []
    scanned = with_disc = 0
    for phrase in PHRASES:
        if scanned >= max_filings:
            break
        try:
            hits = full_text_search(phrase, forms="10-K")
        except Exception as e:
            print(f"  search '{phrase}' ERR {type(e).__name__}")
            continue
        for h in hits:
            if scanned >= max_filings or not h["cik"] or h["cik"] in seen:
                continue
            seen.add(h["cik"])
            supp = by_cik.get(h["cik"], {}).get("ticker")
            if not supp:  # only currently-listed suppliers are tradeable; skip before fetching
                continue
            f = latest_10k(h["cik"])  # fetch the real 10-K, not the FTS-matched fragment
            if not f:
                continue
            acc, doc, dt = f
            try:
                txt = filing_text(h["cik"], acc, doc)
            except Exception:
                continue
            scanned += 1
            disc = extract_disclosures(txt)
            if disc:
                with_disc += 1
            for d in disc:
                cust = resolve(d["customer"], by_name)
                if cust and supp != cust:
                    links.append((supp, cust, d["pct"], dt, d["customer"]))

    uniq = sorted({(s, c) for s, c, *_ in links})
    with open("data/named_links.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["supplier", "customer", "pct", "date", "customer_raw"])
        w.writerows(links)

    print(f"\nscanned filings         : {scanned}")
    print(f"  with any disclosure    : {with_disc}")
    print(f"resolvable named links   : {len(links)}")
    print(f"  distinct supplier->cust: {len(uniq)}")
    print(f"yield (links / filing)   : {len(links) / scanned:.2f}" if scanned else "n/a")
    print("sample:", uniq[:12])
    print("\n-> data/named_links.csv (gitignored)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
