"""Phase C directional check: run the engine on the C-F links that resolve for free.

Only ~two dozen C-F links resolve to current tickers (see phase_c_coverage.py), all
survivors, so this is a DIRECTIONAL SANITY CHECK over the link era (1998-2008), NOT a
rigorous reproduction. Heavy survivorship bias; static links; Tiingo raw tickers.

Run: python3 phase_c_backtest.py
"""
from elp.backtest import long_short_returns, performance
from elp.cf_links import load_cf_links
from elp.edgar import load_ticker_map, resolve
from elp.prices import monthly_returns
from elp.tiingo import fetch_monthly


def resolved_links() -> list[tuple[str, str]]:
    links = load_cf_links()
    permno2name: dict[int, str] = {}
    for r in links:
        if r["customer_permno"] and r["customer_name"]:
            permno2name.setdefault(r["customer_permno"], r["customer_name"])
    _, by_name = load_ticker_map()
    best: dict[str, tuple[str, float]] = {}  # supplier -> (principal customer, concentration)
    for r in links:
        sname = permno2name.get(r["supplier_permno"])
        st = resolve(sname, by_name) if sname else None
        ct = resolve(r["customer_name"], by_name)
        if st and ct and st != ct:
            conc = r.get("concentration") or 0.0
            if st not in best or conc > best[st][1]:
                best[st] = (ct, conc)
    return [(s, c) for s, (c, _) in best.items()]


def main() -> None:
    links = resolved_links()
    tickers = {t for pair in links for t in pair}
    returns = {}
    for t in sorted(tickers):
        try:
            r = monthly_returns(fetch_monthly(t, start="1997-01-01"))
            returns[t] = {k: v for k, v in r.items() if 1998 <= k[0] <= 2008}  # link era
        except Exception as e:
            print(f"  warn {t}: {type(e).__name__}")
    usable = [(s, c) for s, c in links if s in returns and c in returns]
    print(f"resolved links {len(links)} | usable (both priced) {len(usable)}\n")
    for cost in (0.0, 10.0):
        p = performance(long_short_returns(usable, returns, cost_bps=cost))
        if p.get("n"):
            print(f"cost {cost:>4.0f}bps | months {p['n']:>3} | ann_ret {p['ann_return']*100:>6.1f}% "
                  f"| ann_vol {p['ann_vol']*100:>5.1f}% | Sharpe {p['sharpe']:>5.2f} | hit {p['hit_rate']*100:.0f}%")
    print("\n[caveat] ~two dozen SURVIVOR links, 1998-2008, static, raw Tiingo tickers.")
    print("Directional sanity check only — NOT rigorous proof (survivorship bias cuts both ways).")


if __name__ == "__main__":
    main()
