"""Phase D — daily per-trade dynamic engine backtest (directional read, not proof).

Simulates the trailing-stop + signal-exit strategy on daily bars over the hand-curated
universe. Survivorship-biased, in-sample-ish, frozen params — a directional check that
the dynamic overlay behaves sensibly, not a valid alpha estimate.

Run: python3 phase_d_dynamic.py
"""
from elp.links import HIGHSIGNAL_LINKS
from elp.tiingo import fetch_daily
from elp.trades import BORROW_APR, SPREAD_BPS, simulate, trade_stats


def main() -> None:
    links = [(s, c) for s, c, _ in HIGHSIGNAL_LINKS]
    tickers = {t for pair in links for t in pair}
    prices = {}
    for t in sorted(tickers):
        try:
            prices[t] = fetch_daily(t, start="2016-01-01")
        except Exception as e:
            print(f"  warn {t}: {type(e).__name__}")
    links = [(s, c) for s, c in links if s in prices and c in prices]

    closed, opens = simulate(links, prices)
    g = trade_stats(closed)
    if not g.get("n"):
        print("no trades")
        return
    net = trade_stats(closed, SPREAD_BPS, BORROW_APR)
    net2 = trade_stats(closed, SPREAD_BPS * 2, BORROW_APR * 2)  # sensitivity: double costs
    worst = min(t["ret"] for t in closed)
    gapped = sum(1 for t in closed if t["ret"] < -0.08)  # daily stop gapped through the -5% level
    print(f"trades {g['n']} | win {g['win_rate']*100:.0f}% | avg_hold {g['avg_days']:.0f}d | "
          f"exits: {g['stops']} stop / {g['signals']} signal | open now {len(opens)}")
    print(f"expectancy/trade:  GROSS {g['mean_ret']*100:+.2f}%  |  "
          f"NET @{SPREAD_BPS:.0f}bps+{BORROW_APR*100:.0f}%APR {net['mean_ret']*100:+.2f}% "
          f"(win {net['win_rate']*100:.0f}%)  |  NET @2x costs {net2['mean_ret']*100:+.2f}%")
    print(f"worst trade {worst*100:.1f}% | {gapped} trades gapped through the -5% stop (<-8%)")
    print("\nrecent closed trades:")
    for t in sorted(closed, key=lambda x: x["entry_date"])[-8:]:
        side = "L" if t["side"] > 0 else "S"
        print(f"  {t['entry_date']} {side} {t['supplier']:5} (cust {t['customer']:5}) "
              f"-> {t['exit_date']} {t['ret']*100:+.1f}% [{t['reason']}]")
    print("\n[caveat] Per-trade GROSS expectancy on the hand-curated set: survivorship-biased,"
          " in-sample-ish, frozen params, overlapping/correlated trades, NO costs, and daily"
          " marking lets losses gap past the -5% stop. Directional read only, NOT a valid alpha.")


if __name__ == "__main__":
    main()
