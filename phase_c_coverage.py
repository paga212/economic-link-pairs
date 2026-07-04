"""Phase C feasibility: can we resolve Cohen-Frazzini links to tickers for FREE?

The C-F file keys suppliers by CRSP permno (no ticker/name). Trick: it also gives
(customer_permno -> customer_name) for every row, so we harvest a free permno->name
map and use it to name suppliers, then resolve names -> current tickers via the SEC
map. This is survivorship-biased (only firms still listed today resolve) and reported
as such. Measures coverage before building the point-in-time backtest.

Run: python3 phase_c_coverage.py
"""
from elp.cf_links import load_cf_links
from elp.edgar import load_ticker_map, resolve


def main() -> None:
    links = load_cf_links()
    permno2name: dict[int, str] = {}
    for r in links:
        if r["customer_permno"] and r["customer_name"]:
            permno2name.setdefault(r["customer_permno"], r["customer_name"])

    _, by_name = load_ticker_map()
    resolved = []
    supp_named = 0
    for r in links:
        sname = permno2name.get(r["supplier_permno"])
        if sname:
            supp_named += 1
        st = resolve(sname, by_name) if sname else None
        ct = resolve(r["customer_name"], by_name)
        if st and ct and st != ct:
            resolved.append((st, ct, r["fy_end"]))

    pairs = {(s, c) for s, c, _ in resolved}
    yrs = sorted({d.year for _, _, d in resolved if d})
    print(f"C-F link rows                 : {len(links)}")
    print(f"supplier permnos nameable     : {supp_named}  (appear as a customer elsewhere)")
    print(f"rows with BOTH legs resolved  : {len(resolved)}")
    print(f"distinct supplier->customer   : {len(pairs)}")
    print(f"distinct suppliers            : {len({s for s, _ in pairs})}")
    print(f"fiscal years covered          : {yrs[0]}-{yrs[-1]}" if yrs else "none")
    print("sample pairs:", sorted(pairs)[:15])


if __name__ == "__main__":
    main()
