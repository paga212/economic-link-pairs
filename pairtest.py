"""Run the Cohen-Frazzini test battery on the live link universe. Research only; trades nothing.

Signal = the paper's, unchanged: rank suppliers by their principal customer's prior-month
return, long the top slice, short the bottom, equal weight, hold one month (elp/backtest.py).

Reads the placebo percentile as the headline. Everything printed above it is context for it.
Run: python3 pairtest.py
"""
from statistics import median

from elp.links import load_universe
from elp.pairtest import (PASS_THROUGH, market_beta, null_summary, placebo, placebo_pvalue,
                          pooled_stats, screen, screened_sharpe, suppliers_per_month)
from elp.backtest import long_short_returns, performance
from elp.prices import monthly_returns
from elp.tiingo import fetch_monthly

START = "2010-01-01"
PLACEBO_N = 1000
MARKET = "SPY"


def main() -> None:
    links = [(s, c) for s, c, _ in load_universe()]
    tickers = sorted({t for pair in links for t in pair} | {MARKET})
    returns = {}
    for t in tickers:
        try:
            returns[t] = monthly_returns(fetch_monthly(t, start=START))
        except Exception as e:
            print(f"  warn {t}: {type(e).__name__} — dropped")
    links = [(s, c) for s, c in links if s in returns and c in returns]

    print(f"\nuniverse: {len(links)} links, {len({s for s, _ in links})} suppliers, "
          f"months from {START}")

    # ---- screen -------------------------------------------------------------------------
    kept, dropped = screen(links, returns)
    print(f"\nSCREEN  (pass-through customers: {', '.join(sorted(PASS_THROUGH))})")
    for (s, c), reason in dropped:
        print(f"  drop  {s:6} <- {c:6}  {reason}")
    for s, c in kept:
        print(f"  keep  {s:6} <- {c:6}")
    if len(kept) < 2:
        print("\nfewer than 2 links survive: no cross-section, nothing to test.")
        return

    multi = {s for s, _ in kept if sum(1 for a, _ in kept if a == s) > 1}
    if multi:
        print(f"  note  {len(multi)} supplier(s) keep >1 customer ({', '.join(sorted(multi))}); "
              "the engine uses the first by file order as the principal customer.")

    # ---- per-pair diagnostics (context, not a claim) ------------------------------------
    st = pooled_stats(kept, returns)
    print(f"\nPOOLED PAIR STATS  ({st['n_pairs']} pairs, diagnostic only)")
    print(f"  contemporaneous corr {st['contemp_corr']:+.3f}   (link is real if clearly > 0)")
    print(f"  lagged corr          {st['lagged_corr']:+.3f}   (biased up: pairs were screened on it)")
    print(f"  up-minus-down        {st['up_minus_down'] * 100:+.2f}%/mo")

    # ---- portfolio ----------------------------------------------------------------------
    print("\nLONG/SHORT  (rank on prior-month customer return, hold 1 month)")
    for cost in (0.0, 10.0, 25.0):
        p = performance(long_short_returns(kept, returns, cost_bps=cost))
        print(f"  {cost:>4.0f} bps | months {p['n']:>3} | ann_ret {p['ann_return'] * 100:>+6.1f}% "
              f"| ann_vol {p['ann_vol'] * 100:>5.1f}% | sharpe {p['sharpe']:>+5.2f} "
              f"| hit {p['hit_rate'] * 100:>4.1f}%")

    gross = long_short_returns(kept, returns)
    print(f"  market beta vs {MARKET}: {market_beta(gross, returns[MARKET]):+.3f}  "
          "(a rank-formed spread should sit near zero)")

    # ---- power --------------------------------------------------------------------------
    counts = [v for v in suppliers_per_month(kept, returns).values() if v]
    print(f"\nPOWER   suppliers per formation month: min {min(counts)}, "
          f"median {median(counts):.0f}, max {max(counts)}")
    print("        The paper ranked thousands of links. A cross-section this narrow cannot")
    print("        reject much: read a null result as 'no power', not as 'no edge'.")

    # ---- placebo: the headline ----------------------------------------------------------
    real = screened_sharpe(kept, returns)
    null = placebo(links, returns, n=PLACEBO_N)
    ns = null_summary(null)
    print(f"\nPLACEBO  ({ns['n']}/{PLACEBO_N} rewirings survived the same screen)")
    print("  Each draw permutes the customer column across suppliers, preserving every name's")
    print("  own returns and destroying only the pairing, then applies the IDENTICAL screen.")
    print(f"  null sharpe: mean {ns['mean']:+.2f}  sd {ns['sd']:.2f}  "
          f"[p05 {ns['p05']:+.2f}, p95 {ns['p95']:+.2f}]")
    print(f"  real sharpe: {real:+.2f}")
    p = placebo_pvalue(real, null)
    print(f"\n  >>> p = {p:.3f}  (how often a RANDOM rewiring matches or beats the real links)")
    print("  >>> " + ("real links beat the null" if p <= 0.05 else
                      "the real wiring is indistinguishable from a random one"))
    print("\n  The null mean is positive because the full-history lagged screen selects winners")
    print("  even out of noise. That bias is why the real Sharpe is compared to THIS null and")
    print("  never to zero. The p-value is the only number here worth quoting.")


if __name__ == "__main__":
    main()
