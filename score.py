"""Score matured paper-trade recommendations vs realized returns (out-of-sample tracker).

Only recommendations logged BEFORE their holding month count as genuine out-of-sample.
Metrics are currently GROSS (no cost/borrow haircut yet — see kill-rule discussion).

Run: python3 score.py
"""
from elp.paper import fetch_returns, load_entries, score


def main() -> None:
    entries = load_entries()
    if not entries:
        print("no paper_log.jsonl yet — run recommend.py first.")
        return
    rows, t = score(entries, fetch_returns(entries))
    print("matured recommendations:")
    for r in rows:
        h = r["holding"]
        print(f"  {h[0]}-{h[1]:02d}:  long {r['long']*100:+.2f}%  short {r['short']*100:+.2f}%  "
              f"L/S {r['ls']*100:+.2f}%")
    if t["n"]:
        print(f"\ncumulative L/S {t['cum']*100:+.2f}%  |  avg {t['avg']*100:+.2f}%/mo  "
              f"|  hit {t['hit']*100:.0f}%  |  n={t['n']}")
    else:
        print("\nno matured recommendations yet — FORWARD test; check back after holding months complete.")


if __name__ == "__main__":
    main()
