"""Calibration gate: the false-positive rate of the screen+placebo test at the achieved N.

Under the null (no lead-lag), a 5%-level test must reject 5% of the time. If it rejects far more,
its p-value is not a p-value. Run this at the supplier count `pairtest.py` actually achieved,
BEFORE reading pairtest.py's p-value. Synthetic returns only; no network.

Run: python3 calibrate.py [n_suppliers] [trials] [placebo_draws]
"""
import random
import sys
from math import sqrt

from elp.pairtest import placebo, placebo_pvalue, screened_sharpe

MONTHS, SIGMA = 197, 0.10


def _months(n):
    out, y, m = [], 2010, 1
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


MS = _months(MONTHS)


def _null_universe(n, rng):
    """No lead-lag whatsoever: supplier returns are independent of the customer's.

    Every customer and every supplier series is its own independent gaussian draw, so a
    supplier's month-(M+1) return carries zero information about its customer's month-M
    return -- exactly the null the placebo is supposed to test against. Ad hoc probe on this
    exact generator (n=8, 15 trials, 40 placebo draws): mean placebo p-value ~0.58, spread
    roughly across [0.1, 0.95] with no skew toward 0 -- consistent with the intended uniform
    null (noisy at that trial count, but the important thing -- no pileup near 0 -- holds).
    """
    links, R = [], {}
    for i in range(n):
        s, c = f"S{i}", f"C{i}"
        R[c] = {m: rng.gauss(0, SIGMA) for m in MS}
        R[s] = {m: rng.gauss(0, SIGMA) for m in MS}
        links.append((s, c))
    return links, R


def main(n: int = 37, trials: int = 200, draws: int = 400) -> bool:
    """Run the calibration and print the result. Returns True iff the gate passes. Does not
    exit -- callers (including tests) can call this safely; only the __main__ block exits."""
    rng = random.Random(0)
    hits = done = 0
    for t in range(trials):
        links, R = _null_universe(n, rng)
        real = screened_sharpe(links, R)
        if real is None:
            continue
        null = placebo(links, R, n=draws, seed=t)
        if not null:
            continue
        done += 1
        hits += placebo_pvalue(real, null) <= 0.05
    rate = hits / done if done else float("nan")
    se = sqrt(0.05 * 0.95 / done) if done else float("nan")
    print(f"N={n}  trials={done}  placebo draws={draws}")
    print(f"false-positive rate at alpha=0.05: {rate * 100:.1f}%  (target 5.0%, 1 SE = {se * 100:.1f}%)")
    ok = done > 0 and abs(rate - 0.05) <= 2 * se
    print("GATE PASSED - the p-value from pairtest.py is interpretable." if ok else
          "GATE FAILED - do NOT quote pairtest.py's p-value. Raise PLACEBO_N and re-run.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(*[int(a) for a in sys.argv[1:4]]) else 1)
