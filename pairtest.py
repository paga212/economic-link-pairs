"""Run the Cohen-Frazzini test battery on the link universe. Research only; trades nothing.

Signal = the paper's, unchanged: rank suppliers by their principal customer's prior-month
return, long the top slice, short the bottom, equal weight, hold one month (elp/backtest.py).

Reads the point-in-time XBRL universe (xbrl_links.json, built by xbrl_build.py) and reports the
placebo percentile as the headline -- but only after calibrate.py has passed.
Run: python3 xbrl_build.py first (writes xbrl_links.json), then python3 pairtest.py
"""
import json
import os
from statistics import median

from elp.backtest import long_short_returns, performance
from elp.pairtest import (PASS_THROUGH, restrict_pit, market_beta, null_summary, placebo,
                          placebo_pvalue, pooled_stats, screen, screened_sharpe,
                          suppliers_per_month)
from elp.pit import links_asof
from elp.prices import monthly_returns
from elp.tiingo import fetch_monthly

START = "2010-01-01"
PLACEBO_N = 1000
MARKET = "SPY"
LINKS_JSON = "xbrl_links.json"


def _load_dated():
    """The dated point-in-time links from xbrl_links.json. Build it with xbrl_build.py."""
    if not os.path.exists(LINKS_JSON):
        raise SystemExit(f"{LINKS_JSON} not found -- run `python3 xbrl_build.py` first.")
    return json.load(open(LINKS_JSON))


def main() -> None:
    dated = _load_dated()
    pairs = sorted({(r["supplier"], r["customer"]) for r in dated})
    tickers = sorted({t for pair in pairs for t in pair} | {MARKET})

    returns, no_price = {}, []
    for t in tickers:
        try:
            returns[t] = monthly_returns(fetch_monthly(t, start=START))
        except Exception:
            no_price.append(t)
    links = [(s, c) for s, c in pairs if s in returns and c in returns]
    lost = len(pairs) - len(links)
    keep = set(links)
    dated = [r for r in dated if (r["supplier"], r["customer"]) in keep]

    print(f"\nuniverse: xbrl_links.json (point-in-time) | "
          f"{len(links)} links, {len({s for s, _ in links})} suppliers")
    print(f"\nPRICE COVERAGE  {len(no_price)} of {len(tickers)} tickers had no Tiingo history; "
          f"{lost} of {len(pairs)} links dropped.")
    print("        Residual SURVIVORSHIP bias, measured rather than hidden: point-in-time links")
    print("        from 2013 include firms since delisted, which Tiingo covers thinly.")

    if len(links) < 2:
        print("\nfewer than 2 priced links: nothing to test.")
        return

    all_months = sorted({m for t in returns for m in returns[t]})
    pit = links_asof(dated, all_months)

    # ---- screen -------------------------------------------------------------------------
    kept, rejected = screen(links, returns)
    print(f"\nSCREEN  (pass-through customers: {', '.join(sorted(PASS_THROUGH))})")
    reasons = {}
    for _pair, reason in rejected:
        reasons[reason] = reasons.get(reason, 0) + 1
    for reason, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  drop {n:>4}  {reason}")
    print(f"  keep {len(kept):>4}  links, {len({s for s, _ in kept})} suppliers")
    if len(kept) < 2:
        print("\nfewer than 2 links survive: no cross-section, nothing to test.")
        return

    table = restrict_pit(pit, kept) if pit else kept

    # ---- per-pair diagnostics (context, not a claim) ------------------------------------
    st = pooled_stats(kept, returns)
    print(f"\nPOOLED PAIR STATS  ({st['n_pairs']} pairs, diagnostic only)")
    print(f"  contemporaneous corr {st['contemp_corr']:+.3f}   (link is real if clearly > 0)")
    print(f"  lagged corr          {st['lagged_corr']:+.3f}   (biased up: pairs screened on it)")
    print(f"  up-minus-down        {st['up_minus_down'] * 100:+.2f}%/mo")

    # ---- portfolio ----------------------------------------------------------------------
    print("\nLONG/SHORT  (rank on prior-month customer return, hold 1 month)")
    for cost in (0.0, 10.0, 25.0):
        p = performance(long_short_returns(table, returns, cost_bps=cost))
        print(f"  {cost:>4.0f} bps | months {p['n']:>3} | ann_ret {p['ann_return'] * 100:>+6.1f}% "
              f"| ann_vol {p['ann_vol'] * 100:>5.1f}% | sharpe {p['sharpe']:>+5.2f} "
              f"| hit {p['hit_rate'] * 100:>4.1f}%")

    gross = long_short_returns(table, returns)
    print(f"  market beta vs {MARKET}: {market_beta(gross, returns[MARKET]):+.3f}  "
          "(a rank-formed spread should sit near zero)")

    # ---- power --------------------------------------------------------------------------
    counts = [v for v in suppliers_per_month(kept, returns, pit=table).values() if v]
    print(f"\nPOWER   suppliers per formation month: min {min(counts)}, "
          f"median {median(counts):.0f}, max {max(counts)}")
    print("        Target is ~25 (see docs/superpowers/specs/2026-07-09-...): below that the")
    print("        test cannot reject, and a null result means 'no power', not 'no edge'.")

    # ---- placebo: the headline ----------------------------------------------------------
    real = screened_sharpe(kept, returns, pit=table)
    null = placebo(links, returns, n=PLACEBO_N, pit=pit)
    ns = null_summary(null)
    if ns["n"] == 0:
        print("\nplacebo produced no valid rewirings -- the screen is too tight to test")
        return
    print(f"\nPLACEBO  ({ns['n']}/{PLACEBO_N} rewirings survived the same screen)")
    print("  Each draw permutes the customer column across suppliers, preserving every name's")
    print("  own returns and destroying only the pairing, then applies the IDENTICAL screen.")
    print(f"  null sharpe: mean {ns['mean']:+.2f}  sd {ns['sd']:.2f}  "
          f"[p05 {ns['p05']:+.2f}, p95 {ns['p95']:+.2f}]")
    if real is None:
        print("  real sharpe: n/a (screened universe degenerate)")
        return
    print(f"  real sharpe: {real:+.2f}")
    p = placebo_pvalue(real, null)
    print(f"\n  >>> p = {p:.3f}  (how often a RANDOM rewiring matches or beats the real links)")
    print("  >>> " + ("real links beat the null" if p <= 0.05 else
                      "the real wiring is indistinguishable from a random one"))
    print("\n  Quote this p-value ONLY if `python3 calibrate.py <N>` passed. The null mean is")
    print("  positive because the full-history lagged screen selects winners even out of noise;")
    print("  that bias is why the real Sharpe is compared to THIS null and never to zero.")


if __name__ == "__main__":
    main()
