"""Calibration gate: the false-positive rate of the screen+placebo test under a no-effect null.

Under the null (no lead-lag), a 5%-level test must reject 5% of the time. If it rejects far
more, its p-value is not a p-value: the test is ANTI-CONSERVATIVE and manufactures false
positives. Run this at the supplier count `pairtest.py` actually achieved, BEFORE reading
pairtest.py's p-value. Synthetic returns only; no network.

PASS/FAIL IS ONE-SIDED, on the dangerous side only. A test that rejects LESS than 5% of the
time under the null (CONSERVATIVE) cannot manufacture a false positive -- it can only
under-reject, which costs power, never validity. Only an observed rate significantly ABOVE
5% fails the gate; a rate significantly below 5% is reported as CONSERVATIVE and passes. This
was decided from the module's own stated purpose above (catch a test that manufactures false
positives), not assumed -- a prior two-sided criterion also failed conservative runs, which
punishes conservatism for no reason tied to that purpose.

The gate is itself a statistical test and needs enough trials to have power to certify
itself. At the old default (trials=200), 1 SE on a 5% rate is ~1.5%, so the naive two-sided
band is roughly +/-3 points -- wide enough to accept a true rate of 2% or 8%, yet narrow
enough that a correctly-calibrated test fails it about 5% of the time purely by chance. A
shipped run at trials=200 printed 1.0% and FAILED; a pooled 600-trial run across three master
seeds (0, 1, 2; see `seed` param below) gave 9/200, 11/200, 12/200 -- pooled 32/600 = 5.33%,
1 SE = 0.89% -- CALIBRATED. Default trials is now 600, and `done < MIN_DONE` (200) is refused
outright as UNDERPOWERED regardless of the observed rate, so a handful of lucky trials can
never pass (at done=1 the naive band is +/-43 points).

Run: python3 calibrate.py [n_suppliers] [trials] [placebo_draws] [seed]
"""
import random
import sys
from math import sqrt

from elp.pairtest import placebo, placebo_pvalue, screened_sharpe

MONTHS, SIGMA = 197, 0.10
MIN_DONE = 200          # below this, the gate cannot certify itself; refuse regardless of rate


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


def main(n: int = 37, trials: int = 600, draws: int = 400, seed: int = 0) -> bool:
    """Run the calibration and print the result. Returns True iff the gate passes. Does not
    exit -- callers (including tests) can call this safely; only the __main__ block exits.

    `seed` selects the master RNG stream (default 0) so a PASS/FAIL can be checked for
    seed-specificity by re-running with a different value. Per-trial placebo draws use
    `seed * 10_000 + t`, so different master seeds give disjoint placebo seed streams.
    """
    rng = random.Random(seed)
    hits = done = 0
    for t in range(trials):
        links, R = _null_universe(n, rng)
        real = screened_sharpe(links, R)
        if real is None:
            continue
        null = placebo(links, R, n=draws, seed=seed * 10_000 + t)
        if not null:
            continue
        done += 1
        hits += placebo_pvalue(real, null) <= 0.05
    rate = hits / done if done else float("nan")
    se = sqrt(0.05 * 0.95 / done) if done else float("nan")
    print(f"N={n}  trials={done}  placebo draws={draws}  master seed={seed}")

    if done < MIN_DONE:
        print(f"UNDERPOWERED: only {done} trials completed (need >= {MIN_DONE} for the gate "
              f"to be able to certify itself); a PASS here would be nearly meaningless.")
        print("GATE FAILED - do NOT quote pairtest.py's p-value. Raise trials and re-run.")
        return False

    lo, hi = (0.05 - 2 * se) * 100, (0.05 + 2 * se) * 100
    print(f"false-positive rate at alpha=0.05: {rate * 100:.1f}%  (target 5.0%, "
          f"1 SE = {se * 100:.2f}pp, naive two-sided band = [{lo:.2f}%, {hi:.2f}%])")

    if rate - 0.05 > 2 * se:
        print("GATE FAILED - anti-conservative: rejects significantly more than 5% of the "
              "time under the null, so pairtest.py's p-value is not a p-value. Do NOT quote it.")
        return False
    if 0.05 - rate > 2 * se:
        print("CONSERVATIVE: the test under-rejects, so a significant p-value is trustworthy "
              "but power is lost.")
        print("GATE PASSED - the p-value from pairtest.py is interpretable.")
        return True
    print("CALIBRATED")
    print("GATE PASSED - the p-value from pairtest.py is interpretable.")
    return True


if __name__ == "__main__":
    sys.exit(0 if main(*[int(a) for a in sys.argv[1:5]]) else 1)
