# Kill-rule scorecard — design

**Status:** design approved 2026-07-05 (brainstormed with Pierre).
**Builds on:** `paper_state.json` (written by `track.py`: `closed[].ret_net`/`.entry`, `open`,
`stats`), `paper_start.txt` (OOS boundary), and the `dashboard.py` / `email_report.py` renderers.
Operationalizes the Phase-5 kill rule set 2026-07-05 (PLAN §11.8).

## 1. Context and goal

The kill rule currently lives only in prose. Make it a **live, self-scoring panel**: compute the
three pass criteria from the accruing OOS record and show `PENDING / PASS / FAIL` on the dashboard
and in the weekly email. It renders the rule concrete from day one and auto-delivers the verdict
when the record matures.

The bar (PLAN §11.8): pass = **net Sharpe ≥ 0.5** AND **positive net expectancy** AND **≥5
ideas/month**, judged at the **later of** 12 months after `paper_start` and **≥30 closed OOS
trades**. Any miss → FAIL.

## 2. Approach

Pure computation at **render time** — no new pipeline stage, no `*.json`, no LLM. The dashboard
and email already load `paper_state.json`; each calls one pure function and formats the result.

## 3. Component — `elp/killrule.py` (stdlib, pure)

Constants: `SHARPE_MIN = 0.5`, `EXPECTANCY_MIN = 0.0`, `MIN_IDEAS_PER_MONTH = 5.0`,
`MIN_MONTHS = 12`, `MIN_TRADES = 30`, `DAYS_PER_MONTH = 30.44`, `DAYS_PER_YEAR = 365.25`.

- `sharpe(rets: list[float], years: float) -> float | None` — **per-trade** Sharpe annualized at
  the realized trade frequency: `(mean/pstdev) × sqrt(len(rets)/years)`. Returns `None` if
  `len(rets) < 2`, `pstdev == 0`, or `years <= 0`. (Labeled: per-trade net returns, not a
  capital-weighted portfolio Sharpe.)
- `scorecard(state: dict, start: date, today: date) -> dict` computing from
  `closed = state["closed"]`, `open = state["open"]`:
  - `months = (today - start).days / DAYS_PER_MONTH`; `years = (today - start).days / DAYS_PER_YEAR`
  - `n_closed = len(closed)`; `n_ideas = len(closed) + len(open)`
  - `rets = [c["ret_net"] for c in closed]`; `expectancy = mean(rets)` or `None` if empty
  - `sharpe_val = sharpe(rets, years)`
  - `ideas_per_month = n_ideas / months` if `months >= 1` else `None`
  - `gate_open = months >= MIN_MONTHS and n_closed >= MIN_TRADES`
  - criterion flags: `sharpe_ok = sharpe_val is not None and sharpe_val >= SHARPE_MIN`;
    `expectancy_ok = expectancy is not None and expectancy > EXPECTANCY_MIN`;
    `volume_ok = ideas_per_month is not None and ideas_per_month >= MIN_IDEAS_PER_MONTH`
  - `verdict = "PENDING"` if not `gate_open` else (`"PASS"` if all three flags else `"FAIL"`)
  - Returns `{verdict, gate_open, months, n_closed, n_ideas, expectancy, sharpe: sharpe_val,
    ideas_per_month, sharpe_ok, expectancy_ok, volume_ok,
    thresholds: {sharpe: 0.5, expectancy: 0.0, ideas_per_month: 5.0, months: 12, trades: 30}}`.

All arithmetic guards against empty/degenerate input (no closed trades, `months == 0`) — never
raises.

## 4. Display

- `dashboard.py`: a **"Kill-rule scorecard"** panel by the out-of-sample results — a verdict badge
  (PENDING/PASS/FAIL, colored), the three metrics each with a ✓/✗ against its threshold
  (`Sharpe`, `net expectancy`, `ideas/month`), and gate progress (`month {months:.1f}/12`,
  `{n_closed}/30 closed trades`). `None` metrics render as `—`.
- `email_report.py`: a one-line summary — `Kill rule: {verdict} · Sharpe {…} · exp {…}%/trade ·
  {…} ideas/mo · gate {months:.0f}/12mo, {n_closed}/30`.
- A small shared formatter helper may live in `elp/killrule.py` (e.g. `_fmt` for `— / value`) so
  the two renderers stay consistent; each still owns its own markup.

## 5. Testing (offline, stdlib)
`tests/test_killrule.py`:
- `sharpe`: a known return series → expected value (hand-computed); `< 2` trades → `None`;
  zero-variance series → `None`.
- `scorecard`: PENDING before the gate (`< 12` months or `< 30` trades); a synthetic ≥30-trade,
  ≥12-month, positive-mean, ≥5-ideas/month case → PASS with all flags true; a negative-expectancy
  case at the gate → FAIL with `expectancy_ok` false; the 0-closed edge → metrics `None`, verdict
  PENDING, no raise.
- `tests/test_dashboard.py`: the scorecard panel and verdict appear in the rendered HTML.
- `tests/test_email_report.py`: the `Kill rule:` line appears in the rendered email.

## 6. Out of scope
- Any "signal behaving as designed" / decile-monotonicity check (subjective; the digest narrates it).
- Monthly-bucketed or capital-weighted Sharpe (per-trade annualized is the chosen gate metric).
- Changing the engine, the kill-rule thresholds (fixed in §11.8), or emitting a separate artifact.
