"""Phase 2a — deterministic EDGAR customer-link extraction, validated on known suppliers.

For each known supplier, pull its latest 10-K, regex-extract customer-concentration
disclosures, and resolve the customer name to a ticker. Known-answer check: the
Apple suppliers should surface "Apple", etc. Precision is expected to be imperfect —
this measures where the deterministic pass works and where it needs LLM help.

Run: python3 phase2a.py
"""
from elp.edgar import (extract_disclosures, filing_text, latest_10k,
                       load_ticker_map, norm)

# expected (roughly): Apple / Applied Materials / GM / Boeing
KNOWN_SUPPLIERS = ["CRUS", "SWKS", "QRVO", "JBL", "UCTT", "AXL", "SPR"]


def main() -> None:
    by_cik, by_name = load_ticker_map()
    tick2cik = {v["ticker"]: c for c, v in by_cik.items()}
    hits = 0
    for tk in KNOWN_SUPPLIERS:
        cik = tick2cik.get(tk)
        if not cik:
            print(f"{tk}: no CIK in SEC map")
            continue
        f = latest_10k(cik)
        if not f:
            print(f"{tk}: no 10-K found")
            continue
        acc, doc, dt = f
        try:
            disc = extract_disclosures(filing_text(cik, acc, doc))
        except Exception as e:
            print(f"{tk}: fetch/extract ERR {type(e).__name__}: {e}")
            continue
        disc = sorted(disc, key=lambda d: -d["pct"])[:3]
        print(f"\n{tk} (CIK {cik}, 10-K {dt}):")
        if not disc:
            print("  no customer disclosure extracted")
        for d in disc:
            cust = by_name.get(norm(d["customer"]))
            if cust:
                hits += 1
            print(f"  {d['pct']:>4.0f}%  {d['customer']!r:32} -> {cust or '(unresolved)'}")
    print(f"\nresolved customer tickers: {hits} (deterministic pass; unresolved -> LLM later)")


if __name__ == "__main__":
    main()
