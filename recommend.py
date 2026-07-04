"""Live recommender — this month's long/short pair recommendations (forward paper-trade).

Ranks the high-signal link universe by each supplier's principal customer's most-recent
completed-month return, recommends long the top slice / short the bottom, prints them,
and appends the recommendation to paper_log.jsonl (the out-of-sample audit trail).
Recommendations only — no execution. Run monthly. Score realized P&L later with score.py.

Run: python3 recommend.py
"""
import json
from datetime import datetime, timezone

from elp.backtest import signal_ranking
from elp.links import HIGHSIGNAL_LINKS
from elp.prices import monthly_returns
from elp.tiingo import fetch_monthly

LOG = "paper_log.jsonl"
SIDE_FRAC = 0.34


def _next(k):
    y, m = k
    return (y, m + 1) if m < 12 else (y + 1, 1)


def main() -> None:
    links = [(s, c) for s, c, _ in HIGHSIGNAL_LINKS]
    tickers = {t for pair in links for t in pair}
    returns = {}
    for t in sorted(tickers):
        try:
            returns[t] = monthly_returns(fetch_monthly(t, start="2015-01-01"))
        except Exception as e:
            print(f"  warn {t}: {type(e).__name__}")
    links = [(s, c) for s, c in links if s in returns and c in returns]

    ref = returns.get("AAPL") or next(iter(returns.values()))
    M = max(ref)                       # most recent completed month (formation)
    hold = _next(M)                    # holding month the recs apply to
    ranked = signal_ranking(links, returns, M)
    n = len(ranked)
    k = max(1, min(round(n * SIDE_FRAC), n // 2))
    longs, shorts = ranked[:k], ranked[-k:]

    print(f"Formation {M[0]}-{M[1]:02d}  ->  recommendations for holding month {hold[0]}-{hold[1]:02d}")
    print(f"(signal = customer's {M[0]}-{M[1]:02d} return; long top {k} / short bottom {k} of {n})\n")
    print("LONG suppliers (customer did well last month):")
    for s, c, sig in longs:
        print(f"  LONG  {s:5}  cust {c:5}  signal {sig * 100:+.1f}%")
    print("SHORT suppliers (customer did poorly):")
    for s, c, sig in shorts:
        print(f"  SHORT {s:5}  cust {c:5}  signal {sig * 100:+.1f}%")

    rec = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "formation": list(M), "holding": list(hold),
           "longs": [[s, c] for s, c, _ in longs],
           "shorts": [[s, c] for s, c, _ in shorts]}

    existing = []
    try:
        existing = [json.loads(x) for x in open(LOG) if x.strip()]
    except FileNotFoundError:
        pass
    if any(e["holding"] == rec["holding"] for e in existing):
        print(f"\n[skip] a recommendation for holding {hold} is already logged — not re-appending.")
    else:
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"\nlogged -> {LOG}")

    print("[caveat] forward paper-trade of a signal the evidence says is likely weak. "
          "Recommendations only; no execution. Kill if it doesn't clear the bar.")


if __name__ == "__main__":
    main()
