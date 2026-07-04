"""Phase 0 — data spine + signal-direction validation.

Fetches monthly prices (Yahoo, keyless) for a hardcoded set of known
customer->supplier pairs and checks whether the customer's month-M return predicts
the supplier's month-(M+1) return with the right (positive) sign.

Run: python3 phase0.py
"""
from statistics import mean

from elp.links import LINKS
from elp.prices import fetch_monthly, monthly_returns
from elp.signal import evaluate_pair


def main() -> None:
    cache: dict[str, dict] = {}

    def rets(sym: str) -> dict:
        if sym not in cache:
            cache[sym] = monthly_returns(fetch_monthly(sym))
        return cache[sym]

    print(f"{'supp':6} {'cust':6} {'n':>4} {'same_mo':>8} {'lag_corr':>9} {'up-dn%':>8}  note")
    print("-" * 90)
    contemps, corrs, spreads = [], [], []
    for supp, cust, note in LINKS:
        try:
            res = evaluate_pair(rets(cust), rets(supp))
        except Exception as e:  # network / data hiccup on one pair shouldn't kill the run
            print(f"{supp:6} {cust:6}  ERR {type(e).__name__}: {e}")
            continue
        if not res:
            print(f"{supp:6} {cust:6}  insufficient overlapping data")
            continue
        contemps.append(res["contemp_corr"])
        corrs.append(res["lagged_corr"])
        spreads.append(res["up_minus_down"])
        print(f"{supp:6} {cust:6} {res['n']:>4} {res['contemp_corr']:>8.3f} "
              f"{res['lagged_corr']:>9.3f} {res['up_minus_down'] * 100:>7.2f}  {note}")

    if corrs:
        print("\nPOOLED (equal-weight across pairs):")
        print(f"  same-month corr    : {mean(contemps):+.3f}   "
              "(link is real if clearly >0 — customer & supplier co-move)")
        print(f"  lagged corr        : {mean(corrs):+.3f}   "
              "(>0 => customer month-M predicts supplier month-M+1)")
        print(f"  up-minus-down      : {mean(spreads) * 100:+.2f}%   "
              "(supplier next-month return: customer-up months minus customer-down)")
        link = mean(contemps) > 0.15
        lag = mean(corrs) > 0 and mean(spreads) > 0
        if lag:
            verdict = "DIRECTION CONFIRMED (lag present)"
        elif link:
            verdict = "LINK REAL but LAG ABSENT (efficiently priced on these low-inattention names)"
        else:
            verdict = "INCONCLUSIVE on this sample"
        print(f"  verdict            : {verdict}")
    else:
        print("\nNo pairs evaluated (no data).")


if __name__ == "__main__":
    main()
