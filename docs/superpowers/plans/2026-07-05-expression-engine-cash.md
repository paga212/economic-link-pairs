# Expression Engine (Cash) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn each event-driven directional view into a genuine two-legged long/short *idea* (primary leg + a liquidity-selected neutralizing leg), risk-budgeted to $10k max drawdown, managed and exited as one unit.

**Architecture:** Add pure liquidity/expression primitives (`elp/liquidity.py`, `elp/express.py`), extend the data layer for volume (`elp/tiingo.py`) and the pricer for strike snapping (`elp/options.py`), then refactor the daily engine (`elp/trades.py`) to build/mark/exit two-legged ideas instead of lone positions. `track.py`/`dashboard.py` serialize and render both legs.

**Tech Stack:** Python 3, standard library only (no pandas/numpy/new deps). Tiingo daily bars for prices+volume. Existing Black-Scholes pricer for the put-spread short leg.

## Global Constraints

- **stdlib only** — no third-party dependencies (not even pandas/numpy). Copy the existing modules' style.
- **Recommendations only** — never place trades, connect to a broker, or move money.
- **Deterministic core** — no LLM computes any number; identical results across reruns.
- **Frozen params** — engine knobs (thresholds, $10k budget, stop) are module constants; do NOT tune on live data.
- **Offline tests** — every unit test runs with no network (parse/logic factored out of network calls).
- **Prerequisite:** merge PR #2 (`dashboard-trade-details`: `describe_open`, digest note-keying fix) into `main` first, or rebase this branch on it. This plan assumes `elp/trades.py::describe_open` exists.
- **Scope:** CASH expressions only (long stock; short bear-put-spread; pair vs ETF hedge). The **options overlay** (bull-call-spread, optionability gate, $10k-premium leverage) is a **separate later plan**, gated behind PLAN.md §11.9 (positive net-of-cost cash paper alpha).

---

### Task 1: Tiingo daily bars with volume

**Files:**
- Modify: `elp/tiingo.py` (add `_parse_bars`, `fetch_daily_bars`; refactor `fetch_daily` to wrap)
- Test: `tests/test_tiingo.py` (new)

**Interfaces:**
- Produces: `fetch_daily_bars(symbol: str, start: str = "2015-01-01") -> list[tuple[date, float, float]]` returning (date, adjClose, adjVolume) oldest-first; `_parse_bars(rows: list[dict]) -> list[tuple[date, float, float]]`.
- `fetch_daily` keeps its existing `(date, float)` shape (callers unchanged).

- [ ] **Step 1: Write the failing test** (`tests/test_tiingo.py`)

```python
"""Offline unit tests for Tiingo row parsing (no network)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.tiingo import _parse_bars  # noqa: E402


class TestParseBars(unittest.TestCase):
    def test_parses_date_close_volume(self):
        rows = [{"date": "2020-01-02T00:00:00.000Z", "adjClose": 100.0, "adjVolume": 1_000_000},
                {"date": "2020-01-03T00:00:00.000Z", "adjClose": 101.0, "adjVolume": 2_000_000}]
        out = _parse_bars(rows)
        self.assertEqual(out[0], (date(2020, 1, 2), 100.0, 1_000_000.0))
        self.assertEqual(out[1][2], 2_000_000.0)

    def test_falls_back_to_raw_volume(self):
        rows = [{"date": "2020-01-02T00:00:00.000Z", "adjClose": 50.0, "volume": 500_000}]
        self.assertEqual(_parse_bars(rows)[0], (date(2020, 1, 2), 50.0, 500_000.0))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tiingo -v`
Expected: FAIL — `ImportError: cannot import name '_parse_bars'`

- [ ] **Step 3: Write minimal implementation** (edit `elp/tiingo.py`)

Add after `_fetch`:
```python
def _parse_bars(rows: list) -> list[tuple[date, float, float]]:
    """(date, adjusted close, adjusted volume) oldest-first; tolerates missing adjVolume."""
    out: list[tuple[date, float, float]] = []
    for row in rows:
        d = datetime.fromisoformat(row["date"].replace("Z", "")).date()
        vol = row.get("adjVolume", row.get("volume", 0.0))
        out.append((d, float(row["adjClose"]), float(vol or 0.0)))
    return out


def fetch_daily_bars(symbol: str, start: str = "2015-01-01") -> list[tuple[date, float, float]]:
    """Daily (date, adjusted close, adjusted volume) series, oldest first."""
    url = f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?startDate={start}"
    return _parse_bars(_fetch(url, symbol))
```

Replace the body of `fetch_daily` with a wrapper:
```python
def fetch_daily(symbol: str, start: str = "2015-01-01") -> list[tuple[date, float]]:
    """Daily (date, adjusted close) series, oldest first (for the per-trade engine)."""
    return [(d, px) for d, px, _ in fetch_daily_bars(symbol, start)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tiingo -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/tiingo.py tests/test_tiingo.py
git commit -m "feat(tiingo): fetch_daily_bars with volume; fetch_daily wraps it"
```

---

### Task 2: Liquidity primitives

**Files:**
- Create: `elp/liquidity.py`
- Test: `tests/test_liquidity.py`

**Interfaces:**
- Consumes: bars as `list[tuple[date, float, float]]` (date, price, volume) from Task 1.
- Produces:
  - `dollar_adv(bars, window: int = 63) -> float` — mean(price × volume) over the last `window` bars.
  - `is_tradeable(bars, min_price: float = 5.0, min_adv: float = 5_000_000.0) -> bool`.
  - `beta(a_bars, b_bars, window: int = 63) -> float` — trailing beta of `a` returns vs `b` returns over the last `window` overlapping dates; `1.0` if insufficient data.

- [ ] **Step 1: Write the failing test** (`tests/test_liquidity.py`)

```python
"""Offline unit tests for liquidity primitives (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.liquidity import beta, dollar_adv, is_tradeable  # noqa: E402


def bars(prices, vols, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), float(p), float(v))
            for i, (p, v) in enumerate(zip(prices, vols))]


class TestLiquidity(unittest.TestCase):
    def test_dollar_adv_is_mean_price_times_volume(self):
        b = bars([10, 10, 10], [100, 200, 300])   # 1000, 2000, 3000 -> mean 2000
        self.assertAlmostEqual(dollar_adv(b), 2000.0)

    def test_tradeable_gates_on_price_and_adv(self):
        liquid = bars([50] * 63, [1_000_000] * 63)      # $50M ADV, $50 px
        self.assertTrue(is_tradeable(liquid))
        penny = bars([0.07] * 63, [1_000_000] * 63)     # sub-$5 price
        self.assertFalse(is_tradeable(penny))
        thin = bars([50] * 63, [1000] * 63)             # $50k ADV
        self.assertFalse(is_tradeable(thin))

    def test_beta_of_identical_series_is_one(self):
        a = bars([100 * 1.01 ** i for i in range(64)], [1] * 64)
        self.assertAlmostEqual(beta(a, a), 1.0, places=6)

    def test_beta_of_double_moves_is_two(self):
        b = bars([100 * 1.01 ** i for i in range(64)], [1] * 64)
        a = bars([100 * 1.02 ** i for i in range(64)], [1] * 64)  # ~2x the log-returns
        self.assertAlmostEqual(beta(a, b), 2.0, places=1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_liquidity -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elp.liquidity'`

- [ ] **Step 3: Write minimal implementation** (`elp/liquidity.py`)

```python
"""Liquidity + hedge-ratio primitives from daily (date, price, volume) bars. Pure stdlib.

Dollar-ADV gates which names are tradeable/optionable; beta sizes a beta-neutral ETF hedge.
"""
from __future__ import annotations

from statistics import mean

MIN_PRICE, MIN_ADV = 5.0, 5_000_000.0


def dollar_adv(bars: list[tuple], window: int = 63) -> float:
    """Mean dollar volume (price x volume) over the last `window` bars."""
    tail = bars[-window:]
    if not tail:
        return 0.0
    return mean(px * vol for _, px, vol in tail)


def is_tradeable(bars: list[tuple], min_price: float = MIN_PRICE, min_adv: float = MIN_ADV) -> bool:
    """Last price >= floor and dollar-ADV >= floor. Drops penny/illiquid names (and junk links)."""
    if not bars:
        return False
    last_px = bars[-1][1]
    return last_px >= min_price and dollar_adv(bars) >= min_adv


def _rets(bars: list[tuple]) -> dict:
    """date -> simple daily return."""
    out = {}
    for i in range(1, len(bars)):
        p0, p1 = bars[i - 1][1], bars[i][1]
        if p0 > 0:
            out[bars[i][0]] = p1 / p0 - 1.0
    return out


def beta(a_bars: list[tuple], b_bars: list[tuple], window: int = 63) -> float:
    """Trailing beta of a vs b over overlapping dates (cov/var). 1.0 if too little data."""
    ra, rb = _rets(a_bars), _rets(b_bars)
    common = sorted(set(ra) & set(rb))[-window:]
    if len(common) < 20:
        return 1.0
    xs = [rb[d] for d in common]
    ys = [ra[d] for d in common]
    mx, my = mean(xs), mean(ys)
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0:
        return 1.0
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / var
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_liquidity -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/liquidity.py tests/test_liquidity.py
git commit -m "feat(liquidity): dollar_adv, is_tradeable, beta primitives"
```

---

### Task 3: Strike snapping

**Files:**
- Modify: `elp/options.py` (add `snap_strike`)
- Test: `tests/test_options.py` (add a class; file already exists)

**Interfaces:**
- Produces: `snap_strike(px: float) -> float` — nearest listed strike on a realistic grid: $0.50 increments under $25, $1 under $200, $5 at/above $200.

- [ ] **Step 1: Write the failing test** (append to `tests/test_options.py`)

```python
class TestSnapStrike(unittest.TestCase):
    def test_grid_increments(self):
        from elp.options import snap_strike
        self.assertEqual(snap_strike(129.06), 129.0)   # $1 grid in the $25-200 band
        self.assertEqual(snap_strike(143.40), 143.0)
        self.assertEqual(snap_strike(23.30), 23.5)     # $0.50 grid under $25
        self.assertEqual(snap_strike(421.54), 420.0)   # $5 grid at/above $200
```

(If `tests/test_options.py` lacks a `unittest` import at top, it already imports it — verify; the file runs via `unittest`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_options -v`
Expected: FAIL — `ImportError: cannot import name 'snap_strike'`

- [ ] **Step 3: Write minimal implementation** (append to `elp/options.py`)

```python
def snap_strike(px: float) -> float:
    """Nearest listed strike on a realistic grid: $0.50 under $25, $1 under $200, $5 above."""
    step = 0.5 if px < 25 else (1.0 if px < 200 else 5.0)
    return round(px / step) * step
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_options -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add elp/options.py tests/test_options.py
git commit -m "feat(options): snap_strike to a realistic listed-strike grid"
```

---

### Task 4: Expression selector (`build_idea`)

**Files:**
- Create: `elp/express.py`
- Test: `tests/test_express.py`

**Interfaces:**
- Consumes: `is_tradeable`, `beta` (Task 2); `snap_strike`, `bear_put_spread` (Task 3 / existing); trade knobs from `elp.trades` (`TRAIL`, `SPREAD_WIDTH`, `DTE`, `RISK_FREE`).
- Produces:
  - Constants `RISK_BUDGET = 10_000.0`, `HEDGE_ETF = "SPY"`, `STOP = 0.05`.
  - `build_idea(view: dict, day, bars: dict, signaling: dict, used: set) -> dict`.
    - `view`: `{"supplier","customer","side","entry_px","iv"}` (side +1 long / -1 short).
    - `bars`: `{ticker: list[(date,px,vol)]}` (must include `HEDGE_ETF`).
    - `signaling`: `{supplier: signed_signal_today}` (candidate counterparts).
    - `used`: set of tickers already committed to open ideas.
    - Returns an idea dict: `{"supplier","customer","side","entry_date","primary": leg, "neutralizer": leg, "expression": "stock-pair"|"stock-hedge", "risk_cap": "soft", "peak": 0.0}` where each `leg` is `{"role","ticker","direction","instrument","notional", ...spread fields}`.

- [ ] **Step 1: Write the failing test** (`tests/test_express.py`)

```python
"""Offline unit tests for the expression selector (no network)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.express import RISK_BUDGET, STOP, build_idea  # noqa: E402


def liquid_bars(px=50.0, start=date(2020, 1, 1)):
    return [(start + timedelta(days=i), px, 1_000_000.0) for i in range(63)]  # $50M ADV


class TestExpress(unittest.TestCase):
    def _bars(self, extra=None):
        b = {"S": liquid_bars(), "SPY": liquid_bars(400.0), "CP": liquid_bars()}
        if extra:
            b.update(extra)
        return b

    def test_pairs_with_liquid_opposite_counterpart(self):
        # primary long S; CP is signaling short and liquid -> stock pair, opposite directions.
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, date(2020, 3, 1), self._bars(), {"CP": -0.08}, set())
        self.assertEqual(idea["expression"], "stock-pair")
        self.assertEqual(idea["primary"]["direction"], 1)
        self.assertEqual(idea["neutralizer"]["ticker"], "CP")
        self.assertEqual(idea["neutralizer"]["direction"], -1)   # opposite the primary
        self.assertEqual(idea["primary"]["notional"], idea["neutralizer"]["notional"])  # dollar-neutral

    def test_hedges_when_no_liquid_counterpart(self):
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, date(2020, 3, 1), self._bars(), {}, set())  # no signaling counterpart
        self.assertEqual(idea["expression"], "stock-hedge")
        self.assertEqual(idea["neutralizer"]["ticker"], "SPY")
        self.assertEqual(idea["neutralizer"]["direction"], -1)

    def test_skips_used_counterpart(self):
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, date(2020, 3, 1), self._bars(), {"CP": -0.08}, {"CP"})
        self.assertEqual(idea["expression"], "stock-hedge")   # CP taken -> hedge

    def test_risk_budget_sizes_primary_notional(self):
        # cash long, stop = STOP -> notional = RISK_BUDGET / STOP
        view = {"supplier": "S", "customer": "C", "side": 1, "entry_px": 50.0, "iv": 0.4}
        idea = build_idea(view, date(2020, 3, 1), self._bars(), {}, set())
        self.assertAlmostEqual(idea["primary"]["notional"], RISK_BUDGET / STOP)

    def test_short_primary_is_a_snapped_put_spread(self):
        view = {"supplier": "S", "customer": "C", "side": -1, "entry_px": 129.06, "iv": 0.4}
        b = {"S": liquid_bars(129.06), "SPY": liquid_bars(400.0)}
        idea = build_idea(view, date(2020, 3, 1), b, {}, set())
        self.assertEqual(idea["primary"]["instrument"], "spread")
        self.assertEqual(idea["primary"]["k_long"], 129.0)     # snapped from 129.06
        self.assertTrue(idea["primary"]["k_short"] < idea["primary"]["k_long"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_express -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elp.express'`

- [ ] **Step 3: Write minimal implementation** (`elp/express.py`)

```python
"""Expression selector: turn a directional view into a two-legged idea (primary + neutralizer),
choosing a stock pair vs an ETF hedge by liquidity, risk-budgeted to $10k max drawdown.

CASH expressions only (long stock; short defined-risk bear-put-spread). The options overlay
(bull-call-spread, optionability-driven selection, $10k-premium leverage) is a later plan.
Pure stdlib. No number here comes from an LLM.
"""
from __future__ import annotations

from elp.liquidity import beta, is_tradeable
from elp.options import bear_put_spread, snap_strike
from elp.trades import DTE, RISK_FREE, SPREAD_WIDTH, TRAIL

RISK_BUDGET = 10_000.0      # max drawdown per idea (soft, stop-based for cash)
HEDGE_ETF = "SPY"           # broad-market hedge; sector-extensible later
STOP = TRAIL                # cash notional = RISK_BUDGET / STOP


def _primary_leg(view: dict) -> dict:
    """Cash primary leg: long stock, or short bear-put-spread with snapped strikes."""
    notional = RISK_BUDGET / STOP
    if view["side"] > 0:
        return {"role": "primary", "ticker": view["supplier"], "direction": 1,
                "instrument": "stock", "notional": notional, "entry_px": view["entry_px"]}
    s0 = view["entry_px"]
    k_long = snap_strike(s0)
    k_short = snap_strike(s0 * (1 - SPREAD_WIDTH))
    t0 = DTE / 365.0
    debit = bear_put_spread(s0, k_long, k_short, t0, view["iv"], RISK_FREE)
    return {"role": "primary", "ticker": view["supplier"], "direction": -1,
            "instrument": "spread", "notional": notional, "entry_px": s0,
            "S0": s0, "k_long": k_long, "k_short": k_short, "T0": t0,
            "iv": view["iv"], "dte": DTE, "debit": debit}


def _pick_counterpart(view: dict, bars: dict, signaling: dict, used: set):
    """Best opposite-signal, liquid, unused supplier — strongest |signal|, then ticker."""
    want = -view["side"]                          # neutralizer direction = opposite the primary
    cands = [(abs(sig), t) for t, sig in signaling.items()
             if t != view["supplier"] and t not in used
             and (sig > 0) == (want > 0) and t in bars and is_tradeable(bars[t])]
    if not cands:
        return None
    cands.sort(key=lambda x: (-x[0], x[1]))
    return cands[0][1]


def build_idea(view: dict, day, bars: dict, signaling: dict, used: set) -> dict:
    """Two-legged idea: primary leg + a pair-counterpart or ETF-hedge neutralizer."""
    primary = _primary_leg(view)
    notional = primary["notional"]
    cp = _pick_counterpart(view, bars, signaling, used)
    if cp is not None:
        neutralizer = {"role": "neutralizer", "ticker": cp, "direction": -view["side"],
                       "instrument": "stock", "notional": notional,        # dollar-neutral
                       "entry_px": bars[cp][-1][1]}
        expression = "stock-pair"
    else:
        b = beta(bars[view["supplier"]], bars[HEDGE_ETF]) if HEDGE_ETF in bars else 1.0
        neutralizer = {"role": "neutralizer", "ticker": HEDGE_ETF, "direction": -view["side"],
                       "instrument": "stock", "notional": notional * b,    # beta-neutral
                       "entry_px": bars[HEDGE_ETF][-1][1]}
        expression = "stock-hedge"
    return {"supplier": view["supplier"], "customer": view["customer"], "side": view["side"],
            "entry_date": day, "primary": primary, "neutralizer": neutralizer,
            "expression": expression, "risk_cap": "soft", "peak": 0.0}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_express -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add elp/express.py tests/test_express.py
git commit -m "feat(express): build_idea selects stock-pair vs ETF-hedge by liquidity"
```

---

### Task 5: Net-return marking for a two-legged idea

**Files:**
- Modify: `elp/trades.py` (add `idea_return`)
- Test: `tests/test_trades.py` (add a class)

**Interfaces:**
- Consumes: `bear_put_spread` (existing), leg dicts from Task 4.
- Produces: `idea_return(idea: dict, marks: dict, d) -> tuple[float, bool]` — net idea return (per unit primary notional) and expired flag. `marks` is `{ticker: price}`. Net = primary contribution + (neutralizer_notional/primary_notional) × neutralizer contribution; each leg contribution = `direction × (px/entry-1)` for stock, or the spread mark for a spread.

- [ ] **Step 1: Write the failing test** (append to `tests/test_trades.py`)

```python
class TestIdeaReturn(unittest.TestCase):
    def _idea(self, neut_notional):
        from elp.express import RISK_BUDGET, STOP
        n = RISK_BUDGET / STOP
        return {"entry_date": date(2020, 1, 1),
                "primary": {"ticker": "S", "direction": 1, "instrument": "stock",
                            "notional": n, "entry_px": 100.0},
                "neutralizer": {"ticker": "H", "direction": -1, "instrument": "stock",
                                "notional": neut_notional, "entry_px": 50.0}}

    def test_dollar_neutral_pair_nets_the_two_legs(self):
        from elp.express import RISK_BUDGET, STOP
        from elp.trades import idea_return
        idea = self._idea(RISK_BUDGET / STOP)          # equal notionals
        # long S +10%, short H where H +4% -> short loses 4%; net = +10% - 4% = +6%
        ret, expired = idea_return(idea, {"S": 110.0, "H": 52.0}, date(2020, 1, 20))
        self.assertAlmostEqual(ret, 0.06, places=6)
        self.assertFalse(expired)

    def test_beta_weighted_hedge(self):
        from elp.express import RISK_BUDGET, STOP
        from elp.trades import idea_return
        n = RISK_BUDGET / STOP
        idea = self._idea(0.5 * n)                     # beta 0.5 hedge
        # long S +10%; short H +10% weighted 0.5 -> -5%; net +5%
        ret, _ = idea_return(idea, {"S": 110.0, "H": 55.0}, date(2020, 1, 20))
        self.assertAlmostEqual(ret, 0.05, places=6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_trades -v`
Expected: FAIL — `ImportError: cannot import name 'idea_return'`

- [ ] **Step 3: Write minimal implementation** (add to `elp/trades.py`, near `_mark`)

```python
def _leg_ret(leg: dict, px: float, d) -> tuple[float, bool]:
    """Signed return contribution of one leg (as a fraction of its own notional)."""
    if leg["instrument"] == "spread":
        elapsed = (d - leg["_entry_date"]).days
        trem = max(leg["T0"] - elapsed / 365.0, 1e-6)
        val = bear_put_spread(px, leg["k_long"], leg["k_short"], trem, leg["iv"], RISK_FREE)
        return (val - leg["debit"]) / leg["S0"], elapsed >= leg["dte"]
    return leg["direction"] * (px / leg["entry_px"] - 1.0), False


def idea_return(idea: dict, marks: dict, d) -> tuple[float, bool]:
    """Net idea return per unit primary notional, and whether any spread leg expired."""
    p, n = idea["primary"], idea["neutralizer"]
    p.setdefault("_entry_date", idea["entry_date"])
    n.setdefault("_entry_date", idea["entry_date"])
    p_ret, p_exp = _leg_ret(p, marks[p["ticker"]], d)
    n_ret, n_exp = _leg_ret(n, marks[n["ticker"]], d)
    w = n["notional"] / p["notional"]
    return p_ret + w * n_ret, (p_exp or n_exp)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_trades -v`
Expected: PASS (existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add elp/trades.py tests/test_trades.py
git commit -m "feat(trades): idea_return nets primary + weighted neutralizer legs"
```

---

### Task 6: Two-legged lifecycle in `simulate`

**Files:**
- Modify: `elp/trades.py` (new `simulate_ideas`; keep `simulate` for the validation backtest)
- Test: `tests/test_trades.py` (add a class)

**Interfaces:**
- Consumes: `build_idea` (Task 4), `idea_return` (Task 5), existing `_maps`, `_trailing`, `_vol`.
- Produces: `simulate_ideas(links, bars, enter=ENTER, exit_=EXIT, trail=TRAIL, lookback=LOOKBACK) -> tuple[list, list]` returning (closed_ideas, open_ideas). Same signal logic as `simulate`, but each triggered view is built into a two-legged idea via `build_idea` (both legs' tickers marked `used` until the idea closes), marked/exited on `idea_return` net P&L. `bars` is `{ticker: list[(date,px,vol)]}` and must include `HEDGE_ETF`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_trades.py`)

```python
class TestSimulateIdeas(unittest.TestCase):
    def _bars(self, prices, start=date(2020, 1, 1)):
        return [(start + timedelta(days=i), float(p), 1_000_000.0) for i, p in enumerate(prices)]

    def test_long_idea_opens_two_legs_and_stops_on_net(self):
        from elp.trades import simulate_ideas
        # customer C jumps +10% -> long supplier S; no signaling counterpart -> SPY hedge.
        cust = [100] * 10 + [110] * 8
        supp = [100] * 10 + [100, 106, 112, 120, 116, 109, 107, 107]
        spy = [400] * 18
        bars = {"C": self._bars(cust), "S": self._bars(supp), "SPY": self._bars(spy)}
        closed, opens = simulate_ideas([("S", "C")], bars, lookback=5)
        idea = (closed + opens)[0]
        self.assertEqual(idea["primary"]["ticker"], "S")
        self.assertEqual(idea["expression"], "stock-hedge")
        self.assertEqual(idea["neutralizer"]["ticker"], "SPY")

    def test_pairs_two_opposite_signaling_suppliers(self):
        from elp.trades import simulate_ideas
        cust_up = [100] * 10 + [112] * 8       # S1 long
        cust_dn = [100] * 10 + [88] * 8        # S2 short
        flat = [50] * 18
        bars = {"CU": self._bars(cust_up), "CD": self._bars(cust_dn),
                "S1": self._bars(flat), "S2": self._bars(flat), "SPY": self._bars([400] * 18)}
        closed, opens = simulate_ideas([("S1", "CU"), ("S2", "CD")], bars, lookback=5)
        ideas = closed + opens
        pair = next(i for i in ideas if i["expression"] == "stock-pair")
        self.assertIn(pair["neutralizer"]["ticker"], {"S1", "S2"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_trades -v`
Expected: FAIL — `ImportError: cannot import name 'simulate_ideas'`

- [ ] **Step 3: Write minimal implementation** (add to `elp/trades.py`)

```python
def _bars_maps(bars: dict) -> dict:
    """Like _maps but from (date, px, vol) bars; keeps a price-only map for marking."""
    return _maps({t: [(d, px) for d, px, _ in series] for t, series in bars.items()})


def simulate_ideas(links, bars, enter=ENTER, exit_=EXIT, trail=TRAIL, lookback=LOOKBACK):
    """Event-driven two-legged ideas. Returns (closed_ideas, open_ideas). CASH expressions."""
    from elp.express import HEDGE_ETF, build_idea      # local import avoids a cycle
    maps = _bars_maps(bars)
    cust_of: dict[str, str] = {}
    for s, c in links:
        cust_of.setdefault(s, c)
    tr = {c: _trailing(maps[c], lookback) for c in set(cust_of.values()) if c in maps}

    all_dates = sorted({d for s in cust_of for d in maps.get(s, {}).get("dates", [])})
    open_ideas: dict[str, dict] = {}      # keyed by primary supplier
    used: set = set()
    closed: list = []

    for d in all_dates:
        marks = {t: maps[t]["px"][d] for t in maps if d in maps[t]["px"]}
        # 1) manage open ideas on net return
        for s in list(open_ideas):
            idea = open_ideas[s]
            if idea["primary"]["ticker"] not in marks or idea["neutralizer"]["ticker"] not in marks:
                continue
            ret, expired = idea_return(idea, marks, d)
            idea["peak"] = max(idea["peak"], ret)
            csig = tr.get(idea["customer"], {}).get(d)
            reason = None
            if ret <= idea["peak"] - trail:
                reason = "trail_stop"
            elif csig is not None and ((idea["side"] > 0 and csig < exit_) or
                                       (idea["side"] < 0 and csig > -exit_)):
                reason = "signal"
            elif expired:
                reason = "expiry"
            if reason:
                idea.update(exit_date=d, ret=ret, reason=reason, days=(d - idea["entry_date"]).days)
                closed.append(idea)
                used.discard(idea["primary"]["ticker"])
                used.discard(idea["neutralizer"]["ticker"])
                del open_ideas[s]
        # 2) today's signaling pool (for counterpart pairing)
        signaling = {}
        for s, c in cust_of.items():
            csig = tr.get(c, {}).get(d)
            if csig is not None and abs(csig) >= enter:
                signaling[s] = csig
        # 3) open new ideas
        for s, c in cust_of.items():
            if s in open_ideas or s in used or s not in maps or d not in maps[s]["px"]:
                continue
            csig = tr.get(c, {}).get(d)
            if csig is None:
                continue
            side = 1 if csig >= enter else (-1 if csig <= -enter else 0)
            if not side:
                continue
            i = maps[s]["idx"][d]
            view = {"supplier": s, "customer": c, "side": side,
                    "entry_px": maps[s]["px"][d], "iv": _vol(maps[s], i)}
            idea = build_idea(view, d, bars, signaling, used)
            used.add(idea["primary"]["ticker"])
            used.add(idea["neutralizer"]["ticker"])
            open_ideas[s] = idea
    return closed, list(open_ideas.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_trades -v`
Expected: PASS (existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add elp/trades.py tests/test_trades.py
git commit -m "feat(trades): simulate_ideas — event-driven two-legged idea lifecycle"
```

---

### Task 7: Wire `track.py` and `dashboard.py` to ideas

**Files:**
- Modify: `track.py` (fetch bars, run `simulate_ideas`, serialize ideas)
- Modify: `dashboard.py` (render two-legged ideas)
- Test: `tests/test_dashboard.py` (new — offline render check)

**Interfaces:**
- Consumes: `simulate_ideas`, `idea_return` (Tasks 5-6), `fetch_daily_bars` (Task 1).
- Produces: `paper_state.json` `open` rows now shaped as ideas: `{"supplier","customer","side","expression","entry","days","ret","stop","risk_cap","primary": leg, "neutralizer": leg}`; `dashboard.py::idea_row(o) -> str` renders one idea (both legs, plain-English direction).

- [ ] **Step 1: Write the failing test** (`tests/test_dashboard.py`)

```python
"""Offline render check for the dashboard idea row (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard import idea_row  # noqa: E402

IDEA = {"supplier": "SWKS", "customer": "AAPL", "side": -1, "expression": "stock-pair",
        "entry": "2026-06-01", "days": 8, "ret": 0.012, "stop": -0.05, "risk_cap": "soft",
        "primary": {"ticker": "SWKS", "direction": -1, "instrument": "spread", "notional": 200000.0,
                    "k_long": 143.0, "k_short": 129.0, "debit": 3.6, "dte": 45},
        "neutralizer": {"ticker": "QRVO", "direction": 1, "instrument": "stock",
                        "notional": 200000.0, "entry_px": 95.0}}


class TestIdeaRow(unittest.TestCase):
    def test_row_states_direction_legs_and_expression(self):
        html = idea_row(IDEA)
        self.assertIn("SHORT SWKS", html)          # net direction in plain English
        self.assertIn("AAPL", html)                # driving customer
        self.assertIn("QRVO", html)                # neutralizing leg
        self.assertIn("stock-pair", html)          # expression tag
        self.assertIn("143", html)                 # snapped strike shown
        self.assertIn("+1.2%", html)               # net return from state, not a model
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard -v`
Expected: FAIL — `ImportError: cannot import name 'idea_row'`

- [ ] **Step 3: Write minimal implementation**

In `dashboard.py`, add (module level):
```python
def _leg_str(leg):
    d = "long" if leg["direction"] > 0 else "short"
    if leg["instrument"] == "spread":
        return (f"{d} put-spread {leg['k_long']:.0f}/{leg['k_short']:.0f}p "
                f"debit {leg['debit']:.2f} {leg['dte']}DTE")
    return f"{d} {leg['ticker']} @ {leg['entry_px']:.2f}"


def idea_row(o):
    """One idea as an HTML row: plain-English net direction + both legs + expression tag."""
    from html import escape
    direction = "LONG" if o["side"] > 0 else "SHORT"
    cap = "$10k hard" if o.get("risk_cap") == "hard" else "~$10k stop (gap risk)"
    rcls = "pos" if o["ret"] > 0 else "neg"
    return (
        f"<tr><td><b>{direction} {escape(o['supplier'])}</b><br>"
        f"<span class=sub>vs {escape(o['customer'])}</span></td>"
        f"<td>{escape(o['expression'])}</td>"
        f"<td class=sub>primary: {escape(_leg_str(o['primary']))}<br>"
        f"neutralizer: {escape(_leg_str(o['neutralizer']))}</td>"
        f"<td>{escape(o['entry'])}</td><td>{o['days']}d</td>"
        f"<td class={rcls}>{o['ret']*100:+.1f}%</td>"
        f"<td class=sub>{cap}</td></tr>")
```

Replace the open-trades table construction in `dashboard.py::build` to use `idea_row`:
```python
    open_rows = "".join(idea_row(o) for o in s["open"]) or \
        "<tr><td colspan=7 class=muted>no open ideas</td></tr>"
```
and update the open-trades `<table>` header to: `Idea | Expression | Legs | Since | Held | Net | Risk cap`.

In `track.py`: swap `simulate` for `simulate_ideas`, fetch bars with volume, and serialize ideas. Replace the price fetch and open-row build:
```python
from elp.trades import simulate_ideas, idea_return
from elp.tiingo import fetch_daily_bars
from elp.express import HEDGE_ETF
...
    tickers = sorted({x for pair in links for x in pair} | {HEDGE_ETF})
    bars = {}
    for t in tickers:
        try:
            b = fetch_daily_bars(t, start="2016-01-01")
            if b:
                bars[t] = b
        except Exception as e:
            print(f"  warn {t}: {type(e).__name__}")
    links = [(s, c) for s, c in links if s in bars and c in bars]
    closed, opens = simulate_ideas(links, bars)
    marks = {t: bars[t][-1][1] for t in bars}
    last_date = max(b[-1][0] for b in bars.values())
    open_rows = []
    for idea in opens:
        ret, _ = idea_return(idea, marks, last_date)
        open_rows.append({
            "supplier": idea["supplier"], "customer": idea["customer"], "side": idea["side"],
            "expression": idea["expression"], "risk_cap": idea["risk_cap"],
            "entry": idea["entry_date"].isoformat(), "days": (last_date - idea["entry_date"]).days,
            "ret": ret, "stop": idea["peak"] - TRAIL,
            "primary": idea["primary"], "neutralizer": idea["neutralizer"]})
```
(Leave the OOS closed-trade stats block as-is; `idea` dicts carry `ret`/`days`/`reason` after close, so `net_return`/`trade_stats` still apply if `instrument` is read from `idea["primary"]`. If needed, set `idea["side"]`/`idea["instrument"]=idea["primary"]["instrument"]` before scoring — verify in Step 4.)

- [ ] **Step 4: Run test + live smoke**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS (all).
Then live: copy `.tiingo_token` + `.anthropic_key` into the worktree, run `python3 track.py && python3 dashboard.py`; open `site/index.html` and confirm each idea shows net direction, both legs, expression tag, snapped strikes, and the risk-cap label; confirm numbers match `paper_state.json`.

- [ ] **Step 5: Commit**

```bash
git add track.py dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): render two-legged ideas; track.py runs simulate_ideas"
```

---

## Self-Review

**Spec coverage:**
- §2 idea model → Tasks 4, 6. §3 liquidity gates → Task 2. §4 risk sizing ($10k, dollar/beta-neutral) → Tasks 4 (sizing) + 5 (net return). §5 exits (net stop / signal / expiry, both legs together) → Task 6. §6 dashboard (plain-English direction, snapped strikes, risk-cap tag) → Tasks 3, 7. §7 data gaps → surfaced via `risk_cap` tag + the deferred options plan. §8 bad-links (liquidity kills MZTI) → Task 2 `is_tradeable`. §9 architecture → all tasks. §10 sequencing → this plan is the cash phase; options overlay is a separate plan.
- **Gap acknowledged:** `is_optionable`, `bull_call_spread`, and the options-primary selection are intentionally **not** here — they belong to the deferred options-overlay plan (spec §10.2, gated behind Phase-5).

**Placeholder scan:** No TBD/TODO; every code step has concrete code. The one soft spot is Task 7's OOS-scoring note — Step 4 verifies it explicitly rather than leaving it open.

**Type consistency:** `build_idea` returns `{primary, neutralizer, ...}` (Task 4); `idea_return` (Task 5) and `simulate_ideas` (Task 6) consume exactly those keys; `idea_row`/`track.py` (Task 7) read them. Leg dicts use `direction`, `instrument`, `notional`, `entry_px`, and (spreads) `k_long/k_short/debit/dte/S0/T0/iv` consistently across Tasks 4-7. `bars` is `{ticker: [(date,px,vol)]}` everywhere.

## Out of scope (future plans)
- **Options overlay:** `is_optionable`, `bull_call_spread`, options-primary selection, $10k-premium leverage sizing — gated behind Phase-5 (PLAN.md §11.9) and a real options-data feed.
- **NRP-style entity-resolution bad links** — separate data-quality thread.
- **Sector-ETF hedge map** — starts broad-market (SPY); revisit if residual sector beta matters.
