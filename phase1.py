"""Phase 1 (option 1) — exercise the backtest engine on a curated still-listed set.

INTERIM / ENGINE-VALIDATION ONLY. The universe is a handful of well-known,
still-listed supplier->customer pairs priced off keyless Yahoo. This is
survivorship-biased, tiny, and not point-in-time, so the performance numbers below
are NOT a valid alpha estimate — they only show the engine runs end-to-end and
produces sane output. The valid test needs the Cohen-Frazzini neglected-supplier
universe with delisted price data (Phase 2 + a real feed).

Run: python3 phase1.py
"""
from elp.backtest import long_short_returns, performance
from elp.links import CURATED_DIVERSE
from elp.prices import monthly_returns
from elp.tiingo import fetch_monthly  # production price source (all curated names are live)


def main() -> None:
    tickers = {t for pair in CURATED_DIVERSE for t in pair[:2]}
    returns = {}
    for t in sorted(tickers):
        try:
            returns[t] = monthly_returns(fetch_monthly(t))
        except Exception as e:
            print(f"  warn: no data for {t}: {type(e).__name__}")
    links = [(s, c) for s, c, _ in CURATED_DIVERSE if s in returns and c in returns]
    print(f"universe: {len(links)} links, {len(returns)} tickers with data\n")

    for cost in (0.0, 10.0):
        series = long_short_returns(links, returns, cost_bps=cost)
        p = performance(series)
        if not p.get("n"):
            print(f"cost {cost:>4.0f}bps: no months formed")
            continue
        print(f"cost {cost:>4.0f}bps | months {p['n']:>3} | "
              f"ann_ret {p['ann_return'] * 100:>6.1f}% | ann_vol {p['ann_vol'] * 100:>5.1f}% | "
              f"Sharpe {p['sharpe']:>5.2f} | hit {p['hit_rate'] * 100:>4.1f}%")

    print("\n[reminder] survivorship-biased, tiny, non-point-in-time curated set — "
          "engine validation only, NOT a valid alpha estimate.")


if __name__ == "__main__":
    main()
