"""Score matured paper-trade recommendations vs realized returns (out-of-sample tracker).

Reads paper_log.jsonl; for each logged recommendation whose HOLDING month has completed
(prices available), computes the realized equal-weight long/short return and reports the
cumulative paper P&L, average, and hit rate. Only recommendations logged BEFORE their
holding month count as genuine out-of-sample.

Run: python3 score.py
"""
import json

from elp.prices import monthly_returns
from elp.tiingo import fetch_monthly

LOG = "paper_log.jsonl"


def main() -> None:
    try:
        entries = [json.loads(x) for x in open(LOG) if x.strip()]
    except FileNotFoundError:
        print("no paper_log.jsonl yet — run recommend.py first.")
        return

    tickers = {s for e in entries for s, _ in e["longs"] + e["shorts"]}
    returns = {}
    for t in sorted(tickers):
        try:
            returns[t] = monthly_returns(fetch_monthly(t, start="2015-01-01"))
        except Exception as e:
            print(f"  warn {t}: {type(e).__name__}")

    def leg(names, hk):
        vals = [returns[s].get(hk) for s, _ in names if returns.get(s, {}).get(hk) is not None]
        return sum(vals) / len(vals) if vals else None

    cum = wins = scored = 0
    print("matured recommendations:")
    for e in entries:
        hk = tuple(e["holding"])
        lr, sr = leg(e["longs"], hk), leg(e["shorts"], hk)
        if lr is None or sr is None:
            continue  # holding month not complete yet (or missing prices)
        ls = lr - sr
        cum += ls
        wins += ls > 0
        scored += 1
        print(f"  {hk[0]}-{hk[1]:02d}:  long {lr * 100:+.2f}%  short {sr * 100:+.2f}%  L/S {ls * 100:+.2f}%")

    if scored:
        print(f"\ncumulative L/S {cum * 100:+.2f}%  |  avg {cum / scored * 100:+.2f}%/mo  "
              f"|  hit {wins / scored * 100:.0f}%  |  n={scored}")
    else:
        print("\nno matured recommendations yet — this is a FORWARD test; "
              "check back after the holding months complete.")


if __name__ == "__main__":
    main()
