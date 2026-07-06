# Kill-rule Scorecard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live Phase-5 kill-rule scorecard — computed purely from `paper_state.json` at render time — that shows PENDING/PASS/FAIL plus the three gate metrics on the dashboard and in the email.

**Architecture:** One pure stdlib module `elp/killrule.py` (`sharpe`, `scorecard`, `scorecard_line`); the dashboard and email each call it at render time and format the result. No new pipeline stage, no JSON artifact, no LLM.

**Tech Stack:** Python 3 stdlib only (`datetime`, `statistics`). No new deps.

## Global Constraints

- **stdlib only** — no third-party deps.
- **Pure, render-time computation** — no new cron step, no `*.json` output, no LLM.
- **Never raises** on empty/degenerate input (0 closed trades, `months == 0`, zero variance).
- **Fixed thresholds** (PLAN §11.8, do not parameterize away): Sharpe ≥ 0.5, expectancy > 0, ≥ 5 ideas/month, gate = later of 12 months and 30 closed trades.
- **Sharpe = per-trade net returns annualized at realized frequency** `(mean/pstdev) × sqrt(n/years)` — not a capital-weighted portfolio Sharpe.
- **Recommendations only** — display only; changes nothing about trades.
- **Offline tests** — no file/network I/O in the unit suite (call the functions with in-memory dicts).
- **Reference spec:** `docs/superpowers/specs/2026-07-05-killrule-scorecard-design.md`.

---

### Task 1: `elp/killrule.py` — scorecard computation

**Files:**
- Create: `elp/killrule.py`
- Test: `tests/test_killrule.py`

**Interfaces:**
- Produces: `sharpe(rets: list, years: float) -> float | None`;
  `scorecard(state: dict, start: date, today: date) -> dict` (keys: `verdict, gate_open, months,
  n_closed, n_ideas, expectancy, sharpe, ideas_per_month, sharpe_ok, expectancy_ok, volume_ok,
  thresholds`); `scorecard_line(sc: dict) -> str`.

- [ ] **Step 1: Write the failing test** (`tests/test_killrule.py`)

```python
"""Offline tests for the Phase-5 kill-rule scorecard (pure; no I/O)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.killrule import scorecard, scorecard_line, sharpe  # noqa: E402


def _closed(rets):
    return [{"ret_net": r, "entry": "2026-02-01"} for r in rets]


class TestSharpe(unittest.TestCase):
    def test_known_series(self):
        # [0.01,0.03]: mean 0.02, pstdev 0.01 -> per-trade 2.0; annualize sqrt(2/1) -> 2*sqrt(2)
        self.assertAlmostEqual(sharpe([0.01, 0.03], 1.0), 2.0 * 2 ** 0.5, places=6)

    def test_degenerate(self):
        self.assertIsNone(sharpe([0.02], 1.0))          # < 2 trades
        self.assertIsNone(sharpe([0.02, 0.02], 1.0))    # zero variance
        self.assertIsNone(sharpe([0.01, 0.03], 0.0))    # non-positive years


class TestScorecard(unittest.TestCase):
    def test_pending_before_gate(self):
        state = {"closed": _closed([0.01] * 5), "open": [{}]}
        sc = scorecard(state, date(2026, 7, 4), date(2027, 1, 4))   # ~6 months, 5 closed
        self.assertEqual(sc["verdict"], "PENDING")
        self.assertFalse(sc["gate_open"])

    def test_pass_when_gate_open_and_all_met(self):
        rets = [0.005, 0.015] * 33                       # 66 closed, mean 0.01, sd 0.005
        state = {"closed": _closed(rets), "open": []}
        sc = scorecard(state, date(2026, 1, 1), date(2027, 2, 1))   # ~13 months, 66 trades
        self.assertTrue(sc["gate_open"])
        self.assertTrue(sc["sharpe_ok"] and sc["expectancy_ok"] and sc["volume_ok"])
        self.assertEqual(sc["verdict"], "PASS")

    def test_fail_on_negative_expectancy(self):
        rets = [-0.005, -0.015] * 33                     # negative mean
        state = {"closed": _closed(rets), "open": []}
        sc = scorecard(state, date(2026, 1, 1), date(2027, 2, 1))
        self.assertTrue(sc["gate_open"])
        self.assertFalse(sc["expectancy_ok"])
        self.assertEqual(sc["verdict"], "FAIL")

    def test_zero_closed_is_pending_and_safe(self):
        sc = scorecard({"closed": [], "open": [{}, {}]}, date(2026, 7, 4), date(2026, 7, 5))
        self.assertIsNone(sc["expectancy"])
        self.assertIsNone(sc["sharpe"])
        self.assertEqual(sc["verdict"], "PENDING")

    def test_scorecard_line_has_verdict(self):
        sc = scorecard({"closed": [], "open": []}, date(2026, 7, 4), date(2026, 7, 5))
        line = scorecard_line(sc)
        self.assertIn("Kill rule:", line)
        self.assertIn("PENDING", line)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_killrule -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elp.killrule'`

- [ ] **Step 3: Write minimal implementation** (`elp/killrule.py`)

```python
"""Phase-5 kill-rule scorecard (PLAN §11.8). Pure computation from paper_state.json — no I/O, no
LLM. Pass = net Sharpe >= 0.5 AND positive net expectancy AND >= 5 ideas/month, judged at the
later of 12 months after paper_start and >= 30 closed OOS trades. Display only; recommendations
only.
"""
from __future__ import annotations

from datetime import date
from statistics import mean, pstdev

SHARPE_MIN = 0.5
EXPECTANCY_MIN = 0.0
MIN_IDEAS_PER_MONTH = 5.0
MIN_MONTHS = 12
MIN_TRADES = 30
DAYS_PER_MONTH = 30.44
DAYS_PER_YEAR = 365.25


def sharpe(rets: list, years: float) -> float | None:
    """Per-trade net-return Sharpe annualized at the realized trade frequency:
    (mean / pstdev) * sqrt(n / years). None if < 2 trades, zero variance, or non-positive years.
    Per-trade — not a capital-weighted portfolio Sharpe."""
    if len(rets) < 2 or years <= 0:
        return None
    sd = pstdev(rets)
    if sd == 0:
        return None
    return (mean(rets) / sd) * ((len(rets) / years) ** 0.5)


def scorecard(state: dict, start: date, today: date) -> dict:
    """Live kill-rule scorecard. Never raises on empty/degenerate input."""
    closed = state.get("closed") or []
    opens = state.get("open") or []
    days = max((today - start).days, 0)
    months = days / DAYS_PER_MONTH
    years = days / DAYS_PER_YEAR
    n_closed = len(closed)
    n_ideas = n_closed + len(opens)
    rets = [c["ret_net"] for c in closed if "ret_net" in c]
    expectancy = mean(rets) if rets else None
    sharpe_val = sharpe(rets, years)
    ideas_per_month = (n_ideas / months) if months >= 1 else None
    gate_open = months >= MIN_MONTHS and n_closed >= MIN_TRADES
    sharpe_ok = sharpe_val is not None and sharpe_val >= SHARPE_MIN
    expectancy_ok = expectancy is not None and expectancy > EXPECTANCY_MIN
    volume_ok = ideas_per_month is not None and ideas_per_month >= MIN_IDEAS_PER_MONTH
    verdict = "PENDING" if not gate_open else (
        "PASS" if (sharpe_ok and expectancy_ok and volume_ok) else "FAIL")
    return {"verdict": verdict, "gate_open": gate_open, "months": months, "n_closed": n_closed,
            "n_ideas": n_ideas, "expectancy": expectancy, "sharpe": sharpe_val,
            "ideas_per_month": ideas_per_month, "sharpe_ok": sharpe_ok,
            "expectancy_ok": expectancy_ok, "volume_ok": volume_ok,
            "thresholds": {"sharpe": SHARPE_MIN, "expectancy": EXPECTANCY_MIN,
                           "ideas_per_month": MIN_IDEAS_PER_MONTH, "months": MIN_MONTHS,
                           "trades": MIN_TRADES}}


def _fmt(x, pct=False) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.2f}%" if pct else f"{x:.2f}"


def scorecard_line(sc: dict) -> str:
    """One-line plain-text summary for the email."""
    return (f"Kill rule: {sc['verdict']} · Sharpe {_fmt(sc['sharpe'])} · "
            f"exp {_fmt(sc['expectancy'], pct=True)}/trade · "
            f"{_fmt(sc['ideas_per_month'])} ideas/mo · "
            f"gate {sc['months']:.0f}/12mo, {sc['n_closed']}/30 trades")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_killrule -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/killrule.py tests/test_killrule.py
git commit -m "feat(killrule): pure scorecard (sharpe + scorecard + line)"
```

---

### Task 2: Dashboard scorecard panel

**Files:**
- Modify: `dashboard.py` (import; add `_scorecard_html`; compute it in `build`; add placeholder in the doc template)
- Test: `tests/test_dashboard.py` (add a test for `_scorecard_html`)

**Interfaces:**
- Consumes: `elp.killrule.scorecard`.
- Produces: `_scorecard_html(sc: dict) -> str`.

- [ ] **Step 1: Write the failing test** (add to `tests/test_dashboard.py`)

```python
class TestScorecardPanel(unittest.TestCase):
    def test_panel_shows_verdict_and_metrics(self):
        from dashboard import _scorecard_html
        sc = {"verdict": "PENDING", "months": 0.1, "n_closed": 0,
              "sharpe": None, "expectancy": None, "ideas_per_month": None,
              "sharpe_ok": False, "expectancy_ok": False, "volume_ok": False}
        html = _scorecard_html(sc)
        self.assertIn("Kill-rule scorecard", html)
        self.assertIn("PENDING", html)
        self.assertIn("net Sharpe", html)
        self.assertIn("0/30", html)          # gate progress
```

(If `tests/test_dashboard.py` lacks `import unittest`, it is already present — the file has `TestIdeaRow(unittest.TestCase)`. Just append this class before the `if __name__` guard, or after the existing class.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard -v`
Expected: FAIL — `ImportError: cannot import name '_scorecard_html'`

- [ ] **Step 3: Implement** (edit `dashboard.py`)

Add imports near the top (with the other `from elp...` imports and `import json`):

```python
from datetime import date

from elp.killrule import scorecard
```

Add the panel formatter (place it above `def build`, next to `idea_row`):

```python
def _scorecard_html(sc: dict) -> str:
    """Phase-5 kill-rule panel: verdict badge + the three gate metrics with ✓/✗."""
    def f(x, pct=False):
        return "—" if x is None else (f"{x * 100:+.2f}%" if pct else f"{x:.2f}")
    badge = {"PASS": "pos", "FAIL": "neg", "PENDING": "muted"}.get(sc["verdict"], "muted")
    row = lambda ok, label, val, thr: (
        f"<li><b class={'pos' if ok else 'neg'}>{'✓' if ok else '✗'}</b> {label} "
        f"<b>{val}</b> ({thr})</li>")
    return (
        f"<h2>Kill-rule scorecard <span class={badge}>[{escape(sc['verdict'])}]</span></h2>"
        f"<p class=sub>Phase-5 gate (PLAN §11.8): pass needs all three, judged at the later of 12 "
        f"months and 30 closed trades. Gate: month {sc['months']:.1f}/12 · {sc['n_closed']}/30 closed.</p>"
        "<ul>"
        + row(sc["sharpe_ok"], "net Sharpe", f(sc["sharpe"]), "&ge; 0.50")
        + row(sc["expectancy_ok"], "net expectancy", f(sc["expectancy"], pct=True) + "/trade", "&gt; 0")
        + row(sc["volume_ok"], "dealflow", f(sc["ideas_per_month"]) + " ideas/mo", "&ge; 5")
        + "</ul>")
```

In `build()`, after the `oos = ...` block and before `doc = f"""...`, compute the panel (fail-soft if `start` is not a date, e.g. the no-state `"—"`):

```python
    scorecard_html = ""
    try:
        scorecard_html = _scorecard_html(scorecard(s, date.fromisoformat(s["start"]), date.today()))
    except (ValueError, TypeError):
        scorecard_html = ""
```

In the doc template, insert the placeholder immediately before the out-of-sample heading. Change:

```python
<h2>Out-of-sample results (net)</h2>{oos}
```

to:

```python
{scorecard_html}
<h2>Out-of-sample results (net)</h2>{oos}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_dashboard -v` then `python3 dashboard.py` (regenerates `site/index.html` from the current `paper_state.json`; confirm no crash and that "Kill-rule scorecard" appears).
Expected: unit test PASS; `dashboard.py` prints `wrote site/index.html (...)`.

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): kill-rule scorecard panel"
```

---

### Task 3: Email scorecard line

**Files:**
- Modify: `email_report.py` (import; compute + insert the scorecard line in `render`)
- Test: `tests/test_email_report.py` (add a test)

**Interfaces:**
- Consumes: `elp.killrule.scorecard`, `elp.killrule.scorecard_line`.

- [ ] **Step 1: Write the failing test** (add a method to `TestRender` in `tests/test_email_report.py`)

```python
    def test_kill_rule_line_present(self):
        html, text = render(STATE, None)
        for blob in (html, text):
            self.assertIn("Kill rule:", blob)
            self.assertIn("PENDING", blob)     # STATE has 0 closed -> gate not open
```

(`STATE` in that file has `"start": "2026-07-04"` and `"closed": []`, so the verdict is PENDING.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_email_report -v`
Expected: FAIL — `AssertionError: 'Kill rule:' not found`

- [ ] **Step 3: Implement** (edit `email_report.py`)

Add imports (with the other stdlib/`elp` imports at the top):

```python
from datetime import date

from elp.killrule import scorecard, scorecard_line
```

(There is already `from datetime import datetime, timezone` — extend it to `from datetime import date, datetime, timezone` rather than adding a second line.)

In `render(state, digest)`, before building `html`/`text`, compute the line (fail-soft):

```python
    try:
        kill_line = scorecard_line(scorecard(state, date.fromisoformat(state["start"]), date.today()))
    except (ValueError, TypeError):
        kill_line = ""
```

Add it to the HTML — insert this fragment into the `html = (...)` concatenation right before the `<h2 ...>Out-of-sample results (net)</h2>` line:

```python
            + (f'<p style="color:#555;font-size:13px">{escape(kill_line)}</p>' if kill_line else '')
```

And add it to the plain-text `text = (...)` concatenation right before the `Out-of-sample results:` line:

```python
            + (f"{kill_line}\n\n" if kill_line else "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_email_report -v` then the full suite `python3 -m unittest discover -s tests`.
Expected: PASS; full suite OK.

- [ ] **Step 5: Commit**

```bash
git add email_report.py tests/test_email_report.py
git commit -m "feat(email): kill-rule scorecard line"
```

---

## Verification (whole feature)

1. **Full offline suite:** `python3 -m unittest discover -s tests` → OK.
2. **Dashboard render:** `python3 dashboard.py` → open `site/index.html`, confirm the "Kill-rule scorecard" panel shows `[PENDING]`, `month 0.x/12`, `0/30 closed`, and the three metrics as `—` with ✗ (0 closed trades today).
3. **Email render:** `EMAIL_DRYRUN=1 python3 email_report.py` → `email_report.eml` contains a `Kill rule: PENDING …` line.

## Self-Review

**Spec coverage:** §3 module (`sharpe`/`scorecard`/`scorecard_line`) → Task 1. §4 dashboard panel → Task 2; email line → Task 3. §5 testing → tests in every task (sharpe known-series + degenerate; scorecard PENDING/PASS/FAIL/0-closed; dashboard panel; email line). §2 render-time/no-artifact and §6 out-of-scope honored (no engine change, no JSON, fixed thresholds).

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `scorecard(state, start, today)` returns the exact key set consumed by `_scorecard_html` (Task 2) and `scorecard_line` (Task 1) — `verdict, months, n_closed, sharpe, expectancy, ideas_per_month, sharpe_ok, expectancy_ok, volume_ok`. `sharpe(rets, years)` signature matches its call inside `scorecard`. Both `dashboard.py` and `email_report.py` parse `state["start"]` via `date.fromisoformat` guarded by `except (ValueError, TypeError)`.

## Out of scope
- Monthly-bucketed / capital-weighted Sharpe; any "signal behaving as designed" check; changing the thresholds or the engine.
