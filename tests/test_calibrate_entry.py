"""Offline test: the calibrate.py gate's PASS/FAIL logic and its __main__ exit path.

Fully mocked: `calibrate.screened_sharpe` and `calibrate.placebo` are monkeypatched so no
real screen/placebo computation runs (see the brief -- this must stay under a second, not
run 200 real trials). `_null_universe` itself is left real; it is cheap stdlib random.gauss
calls with no economics, so it costs nothing to actually run.
"""
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calibrate as entry  # noqa: E402
import elp.pairtest as pairtest_mod  # noqa: E402

_ORIG_SHARPE, _ORIG_PLACEBO = entry.screened_sharpe, entry.placebo


class TestMainReturnValue(unittest.TestCase):
    """Direct calls to calibrate.main(): it must return a bool, not exit."""

    def tearDown(self):
        entry.screened_sharpe, entry.placebo = _ORIG_SHARPE, _ORIG_PLACEBO

    # draws must be >= 19 so the minimum achievable p-value, 1/(draws+1), can actually
    # reach <= 0.05 -- otherwise a "reject" case can never reject regardless of the null.
    DRAWS = 25

    def test_pass_near_5_percent(self):
        # Real stat always available; placebo hits (rejects) exactly 1-in-20 trials -> 5.0%.
        entry.screened_sharpe = lambda links, returns: 1.0
        entry.placebo = lambda links, returns, n, seed: (
            [0.0] * n if seed % 20 == 0 else [2.0] * n)  # 0.0 < real -> reject; 2.0 >= real -> not

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = entry.main(n=6, trials=200, draws=self.DRAWS)

        self.assertIs(ok, True)
        self.assertIn("GATE PASSED", buf.getvalue())
        self.assertIn("trials=200", buf.getvalue())

    def test_fail_far_from_5_percent(self):
        # Force every trial to reject -> observed rate 100%, nowhere near 5%.
        entry.screened_sharpe = lambda links, returns: 1.0
        entry.placebo = lambda links, returns, n, seed: [0.0] * n  # always < real -> always reject

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = entry.main(n=6, trials=50, draws=self.DRAWS)

        self.assertIs(ok, False)
        self.assertIn("GATE FAILED", buf.getvalue())

    def test_rate_uses_done_not_attempted_trials(self):
        # First 50 calls to screened_sharpe produce no statistic (skipped); the remaining
        # 200 (of 250 attempted) are "done". Exactly 10 of those 200 reject -> 5.0%.
        calls = {"n": 0}

        def fake_sharpe(links, returns):
            calls["n"] += 1
            return None if calls["n"] <= 50 else 1.0

        def fake_placebo(links, returns, n, seed):
            return [0.0] * n if 50 <= seed < 60 else [2.0] * n

        entry.screened_sharpe, entry.placebo = fake_sharpe, fake_placebo

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = entry.main(n=6, trials=250, draws=self.DRAWS)

        out = buf.getvalue()
        self.assertIn("trials=200", out)         # done, not the 250 attempted
        self.assertNotIn("trials=250", out)
        self.assertIn("5.0%", out)
        self.assertIs(ok, True)


class TestMainDoesNotExitOnImport(unittest.TestCase):
    def test_calling_main_directly_does_not_raise_systemexit(self):
        # Always rejects -> 100% -> anti-conservative -> FAIL. (Not the old "never rejects"
        # case: under the one-sided criterion a 0% rate is CONSERVATIVE and now PASSES --
        # see TestOneSidedCriterion below. This case still needs a legitimate FAIL to check
        # main() returns rather than exits.)
        entry.screened_sharpe = lambda links, returns: 1.0
        # draws=25 (>= 19) so the minimum achievable p-value, 1/(draws+1), can reach <= 0.05.
        entry.placebo = lambda links, returns, n, seed: [0.0] * n  # always rejects -> 100%
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                # trials=200 (== MIN_DONE) so this is not merely UNDERPOWERED.
                ok = entry.main(n=4, trials=200, draws=25)
            self.assertIs(ok, False)   # returned, did not exit
        finally:
            entry.screened_sharpe, entry.placebo = _ORIG_SHARPE, _ORIG_PLACEBO


class TestOneSidedCriterion(unittest.TestCase):
    """Problem 3: the gate must be one-sided against ANTI-conservative tests only. A
    CONSERVATIVE test (under-rejects) cannot manufacture a false positive, so it must PASS,
    not FAIL -- the old two-sided `abs(rate - 0.05) <= 2*se` criterion got this wrong."""

    def tearDown(self):
        entry.screened_sharpe, entry.placebo = _ORIG_SHARPE, _ORIG_PLACEBO

    def test_anti_conservative_fails(self):
        # Every trial rejects -> 100% -> far above 5% -> FAIL.
        entry.screened_sharpe = lambda links, returns: 1.0
        entry.placebo = lambda links, returns, n, seed: [0.0] * n

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = entry.main(n=6, trials=200, draws=25)

        self.assertIs(ok, False)
        self.assertIn("GATE FAILED", buf.getvalue())

    def test_conservative_passes_and_prints_conservative_line(self):
        # Every trial fails to reject -> 0% -> far below 5% -> CONSERVATIVE, not a failure.
        entry.screened_sharpe = lambda links, returns: 1.0
        entry.placebo = lambda links, returns, n, seed: [2.0] * n

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = entry.main(n=6, trials=200, draws=25)

        out = buf.getvalue()
        self.assertIs(ok, True)
        self.assertIn(
            "CONSERVATIVE: the test under-rejects, so a significant p-value is "
            "trustworthy but power is lost.", out)
        self.assertIn("GATE PASSED", out)


class TestUnderpowered(unittest.TestCase):
    """Problem 1: the gate must refuse to certify itself from too few trials, regardless of
    how good the observed rate looks."""

    def tearDown(self):
        entry.screened_sharpe, entry.placebo = _ORIG_SHARPE, _ORIG_PLACEBO

    def test_done_below_min_done_fails_even_at_exactly_5_percent(self):
        # 199 < MIN_DONE (200). Rate is dead on target (10/199 close to 5%, but that must not
        # matter): rejects on seed%20==0 among 199 trials -> 10/199 ~= 5.03%, essentially 5%.
        entry.screened_sharpe = lambda links, returns: 1.0
        entry.placebo = lambda links, returns, n, seed: (
            [0.0] * n if seed % 20 == 0 else [2.0] * n)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = entry.main(n=6, trials=199, draws=25)

        self.assertIs(ok, False)
        self.assertIn("UNDERPOWERED", buf.getvalue())


class TestSeedThreading(unittest.TestCase):
    """Problem 2: `seed` must reach both the master RNG and the per-trial placebo seed
    stream, and different master seeds must give disjoint placebo seed streams."""

    def tearDown(self):
        entry.screened_sharpe, entry.placebo = _ORIG_SHARPE, _ORIG_PLACEBO

    def _collect_placebo_seeds(self, seed):
        seen = []
        entry.screened_sharpe = lambda links, returns: 1.0

        def fake_placebo(links, returns, n, seed):
            seen.append(seed)
            return [2.0] * n

        entry.placebo = fake_placebo
        with contextlib.redirect_stdout(io.StringIO()):
            entry.main(n=4, trials=3, draws=5, seed=seed)
        return seen

    def test_different_master_seeds_give_disjoint_placebo_seed_streams(self):
        seeds_0 = self._collect_placebo_seeds(0)
        seeds_1 = self._collect_placebo_seeds(1)

        self.assertTrue(seeds_0)
        self.assertTrue(seeds_1)
        self.assertFalse(set(seeds_0) & set(seeds_1))


class TestMainExitPath(unittest.TestCase):
    """The __main__ guard: `python3 calibrate.py ...` must sys.exit(0) on pass, nonzero on
    fail. Exercised in-process via runpy so the real script bottom runs, with the expensive
    functions patched at their source (elp.pairtest) so runpy's fresh `from elp.pairtest
    import ...` picks up the fakes."""

    def setUp(self):
        self._orig_sharpe = pairtest_mod.screened_sharpe
        self._orig_placebo = pairtest_mod.placebo

    def tearDown(self):
        pairtest_mod.screened_sharpe = self._orig_sharpe
        pairtest_mod.placebo = self._orig_placebo

    def _run(self, argv_tail):
        import runpy
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "calibrate.py")
        old_argv = sys.argv
        sys.argv = ["calibrate.py"] + argv_tail
        try:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                with self.assertRaises(SystemExit) as cm:
                    runpy.run_path(path, run_name="__main__")
            return cm.exception.code, buf.getvalue()
        finally:
            sys.argv = old_argv

    def test_exits_zero_on_pass(self):
        pairtest_mod.screened_sharpe = lambda *a, **k: 1.0
        pairtest_mod.placebo = lambda links, returns, n=0, seed=0: (
            [0.0] * n if seed % 20 == 0 else [2.0] * n)
        code, out = self._run(["6", "200", "25"])   # draws=25 >= 19, so rejects can register
        self.assertEqual(code, 0)
        self.assertIn("GATE PASSED", out)

    def test_exits_nonzero_on_fail(self):
        pairtest_mod.screened_sharpe = lambda *a, **k: 1.0
        pairtest_mod.placebo = lambda links, returns, n=0, seed=0: [0.0] * n  # always reject
        code, out = self._run(["6", "50", "25"])
        self.assertNotEqual(code, 0)
        self.assertIn("GATE FAILED", out)


if __name__ == "__main__":
    unittest.main()
