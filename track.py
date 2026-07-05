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

from elp.links import load_universe
from elp.tiingo import fetch_daily
from elp.trades import (BORROW_APR, SPREAD_BPS, TRAIL, _mark, net_return, simulate, trade_stats)

START_FILE, STATE_FILE = "paper_start.txt", "paper_state.json"


def _paper_start() -> date:
    if os.path.exists(START_FILE):
        return date.fromisoformat(open(START_FILE).read().strip())
    d = datetime.now(timezone.utc).date()
    open(START_FILE, "w").write(d.isoformat())
    return d


def main() -> None:
    links = [(s, c) for s, c, _ in load_universe()]
    prices = {}
    for t in sorted({x for pair in links for x in pair}):
        try:
            p = fetch_daily(t, start="2016-01-01")
            if p:
                prices[t] = p
        except Exception as e:
            print(f"  warn {t}: {type(e).__name__}")
    links = [(s, c) for s, c in links if s in prices and c in prices]
    start = _paper_start()

    closed, opens = simulate(links, prices)
    fwd = [t for t in closed if t["entry_date"] >= start]        # out-of-sample only
    last = {t: prices[t][-1] for t in prices}

    open_rows = []
    for t in opens:
        d, px = last[t["supplier"]]
        ret, _ = _mark(t, px, d)
        open_rows.append({
            "supplier": t["supplier"], "customer": t["customer"],
            "kind": "LONG stock" if t["side"] > 0 else "SHORT put-spread",
            "entry": t["entry_date"].isoformat(), "days": (d - t["entry_date"]).days,
            "ret": ret, "stop": t["peak"] - TRAIL})

    st = trade_stats(fwd, SPREAD_BPS, BORROW_APR)
    print(f"paper start {start} | open {len(open_rows)} | OOS closed {st.get('n', 0)}")
    for o in sorted(open_rows, key=lambda x: x["entry"]):
        print(f"  {o['kind']:16} {o['supplier']:5} (cust {o['customer']:5}) since {o['entry']} "
              f"{o['days']:>3}d  ret {o['ret'] * 100:+.1f}%  stop {o['stop'] * 100:+.1f}%")
    if st.get("n"):
        cum = sum(net_return(t, SPREAD_BPS, BORROW_APR) for t in fwd)
        print(f"OOS net: {st['n']} trades | win {st['win_rate'] * 100:.0f}% | "
              f"expectancy {st['mean_ret'] * 100:+.2f}%/trade | cum {cum * 100:+.1f}%")
    else:
        print("OOS net: no closed trades since paper start yet — forward test just begun.")

    state = {
        "generated_utc": datetime.now(timezone.utc).isoformat(), "start": start.isoformat(),
        "open": open_rows,
        "closed": [{"supplier": t["supplier"], "customer": t["customer"],
                    "kind": "LONG" if t["side"] > 0 else "SHORT",
                    "entry": t["entry_date"].isoformat(), "exit": t["exit_date"].isoformat(),
                    "days": t["days"], "reason": t["reason"],
                    "ret_net": net_return(t, SPREAD_BPS, BORROW_APR)} for t in fwd],
        "stats": {k: st.get(k) for k in ("n", "win_rate", "mean_ret")}}
    json.dump(state, open(STATE_FILE, "w"), indent=1)
    print(f"\nwrote {STATE_FILE}")
    print("[caveat] forward OOS paper-trade, net of costs (spread shorts = Grade-C optimistic). "
          "Recommendations only, no execution. Judged against the 12-month kill rule.")


if __name__ == "__main__":
    main()
