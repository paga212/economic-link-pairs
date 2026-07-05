"""Live daily tracker for the dynamic per-trade strategy (out-of-sample paper trade).

Runs the engine on daily data, reports OPEN trades (live stop + unrealized return) and
CLOSED trades entered on/after the paper-start date (the genuine OOS record), net of costs.
Writes paper_state.json (dashboard + audit trail) and sets paper_start.txt on first run.
Recommendations only — no execution.

Run: python3 track.py
"""
import json
import os
from datetime import date, datetime, timezone

from elp.express import HEDGE_ETF
from elp.links import load_universe
from elp.tiingo import fetch_daily_bars
from elp.trades import (BORROW_APR, SPREAD_BPS, TRAIL, idea_return, net_return, simulate_ideas,
                         trade_stats)

START_FILE, STATE_FILE = "paper_start.txt", "paper_state.json"


def _clean_leg(leg: dict) -> dict:
    """JSON-safe copy of a leg dict: idea_return() sets an internal `_entry_date` (a date
    object, not JSON-serializable) on primary/neutralizer via setdefault; strip it here
    rather than in the shared engine code."""
    return {k: v for k, v in leg.items() if not k.startswith("_")}


def _paper_start() -> date:
    if os.path.exists(START_FILE):
        return date.fromisoformat(open(START_FILE).read().strip())
    d = datetime.now(timezone.utc).date()
    open(START_FILE, "w").write(d.isoformat())
    return d


def main() -> None:
    links = [(s, c) for s, c, _ in load_universe()]
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
    start = _paper_start()

    closed, opens = simulate_ideas(links, bars)
    marks = {t: bars[t][-1][1] for t in bars}
    last_date = max(b[-1][0] for b in bars.values())

    open_rows = []
    for idea in opens:
        ret, _ = idea_return(idea, marks, last_date)
        open_rows.append({
            "supplier": idea["supplier"], "customer": idea["customer"], "side": idea["side"],
            "kind": "LONG" if idea["side"] > 0 else "SHORT",
            "expression": idea["expression"], "risk_cap": idea["risk_cap"],
            "entry": idea["entry_date"].isoformat(), "days": (last_date - idea["entry_date"]).days,
            "ret": ret, "stop": idea["peak"] - TRAIL,
            "primary": _clean_leg(idea["primary"]), "neutralizer": _clean_leg(idea["neutralizer"])})

    fwd = [idea for idea in closed if idea["entry_date"] >= start]     # out-of-sample only
    # Controller decision (Task 7): closed items are now two-legged IDEA dicts, not the
    # old single-leg trade dicts. Bridge them into the existing single-leg
    # trade_stats/net_return scoring by setting `instrument` from the primary leg (the
    # idea already carries `side` and `ret`). This is a SINGLE-LEG cost approximation
    # applied to a two-legged idea -- it charges transaction cost once and (for stock
    # shorts) borrow on the primary leg only, ignoring the neutralizer leg's own
    # cost/borrow. A precise two-leg transaction/borrow cost model is a deliberate
    # FOLLOW-UP, out of scope here (YAGNI). Low-stakes today: 0 closed OOS ideas.
    for idea in fwd:
        idea["instrument"] = idea["primary"]["instrument"]

    st = trade_stats(fwd, SPREAD_BPS, BORROW_APR)
    print(f"paper start {start} | open {len(open_rows)} | OOS closed {st.get('n', 0)}")
    for o in sorted(open_rows, key=lambda x: x["entry"]):
        print(f"  {o['expression']:12} {o['supplier']:5} (cust {o['customer']:5}) since {o['entry']} "
              f"{o['days']:>3}d  ret {o['ret'] * 100:+.1f}%")
    if st.get("n"):
        cum = sum(net_return(idea, SPREAD_BPS, BORROW_APR) for idea in fwd)
        print(f"OOS net: {st['n']} trades | win {st['win_rate'] * 100:.0f}% | "
              f"expectancy {st['mean_ret'] * 100:+.2f}%/trade | cum {cum * 100:+.1f}%")
    else:
        print("OOS net: no closed trades since paper start yet — forward test just begun.")

    state = {
        "generated_utc": datetime.now(timezone.utc).isoformat(), "start": start.isoformat(),
        "open": open_rows,
        "closed": [{"supplier": idea["supplier"], "customer": idea["customer"],
                    "kind": "LONG" if idea["side"] > 0 else "SHORT",
                    "entry": idea["entry_date"].isoformat(), "exit": idea["exit_date"].isoformat(),
                    "days": idea["days"], "reason": idea["reason"],
                    "ret_net": net_return(idea, SPREAD_BPS, BORROW_APR)} for idea in fwd],
        "stats": {k: st.get(k) for k in ("n", "win_rate", "mean_ret")}}
    json.dump(state, open(STATE_FILE, "w"), indent=1)
    print(f"\nwrote {STATE_FILE}")
    print("[caveat] forward OOS paper-trade, net of costs (spread shorts = Grade-C optimistic; "
          "OOS closed-trade cost scoring is a single-leg approximation on two-legged ideas). "
          "Recommendations only, no execution. Judged against the 12-month kill rule.")


if __name__ == "__main__":
    main()
