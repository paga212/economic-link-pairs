# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: live forward paper-trade

This is an active git repository (~25 commits). The live system is a **dynamic
per-trade forward paper-trade** of the customer-supplier lead-lag strategy: it
runs the engine on daily data, opens/manages trades (trailing stop + signal
exit), and scores out-of-sample closed trades net of costs. **Recommendations
only — it never executes, connects to a broker, or moves money.** See
`PLAN.md` for the full design and `NOTES.md` for the build log.

Built so far: Phase 0 (data spine + signal check), Phase 1 (backtest engine),
Phase 2a (EDGAR extractor), Phase D (dynamic per-trade engine), Phase B
(LLM-diversified link universe), Phase 3 (Fable-5 daily digest), the paired
long/short expression engine, link validation, and Phase 4 delivery (dashboard +
weekly email). Deliberately **stdlib-only — no third-party deps** (no
pandas/numpy); Tiingo is the production price source.

### Run
```
python3 -m unittest discover -s tests   # 71 offline logic tests
python3 track.py                         # daily tick → paper_state.json (needs Tiingo token)
python3 digest.py                        # Fable-5 daily digest → digest.json (needs Anthropic key)
python3 dashboard.py                     # paper_state.json (+ digest.json) → site/index.html
EMAIL_DRYRUN=1 python3 email_report.py   # render the weekly email → email_report.eml (no send)
```
`run_paper.sh` chains track → digest → dashboard → serve → commit/push (cron `0 22 * * 1-5`).
The weekly email is delivered from the cloud by GitHub Actions
(`.github/workflows/weekly-email.yml`, Mondays 08:00 UTC), independent of this machine.

### Architecture (deterministic core; LLM owns orchestration/parsing only)
- `elp/trades.py` — dynamic per-trade engine (entry signal, trailing stop, exits, net-of-cost stats)
- `elp/express.py` — expression engine: turns each signal into a paired two-legged long/short idea (primary leg + liquidity-chosen neutralizer / ETF hedge)
- `elp/liquidity.py` — tradeability / dollar-ADV gate used by the expression engine and link validation
- `elp/linkcheck.py` — link validation (price-sanity + name↔ticker checks; quarantines bad links to `rejected_links.json`)
- `elp/options.py` — Black-Scholes bear-put-spread pricer (defined-risk short leg, Grade-C IV)
- `elp/signal.py` — prior-month customer return → supplier signal
- `elp/digest.py` — Fable-5 Master/Orchestrator daily digest (ranks/narrates open trades; never emits a number)
- `elp/backtest.py` — monthly cross-sectional long/short engine (engine validation)
- `elp/links.py` — `load_universe()` over the diversified link table (`universe_links.json`)
- `elp/llm.py` — LLM link extraction + `complete_fallback` (Fable-5 → Opus-4.8) (Phase B / Phase 3)
- `elp/tiingo.py` — production prices (`fetch_daily`); `elp/prices.py` — keyless Yahoo prototype
- `elp/edgar.py`, `elp/cf_links.py` — SEC EDGAR extractor; free Cohen-Frazzini link-file parser
- Entry scripts: `track.py`, `digest.py`, `dashboard.py`, `email_report.py`, `linkcheck.py`, and the `phase0/1/2a/2a_build/b_build/c_backtest/c_coverage/d_dynamic.py` phase drivers
- Delivery: `dashboard.py` → `site/index.html` (served by `serve.sh`); `email_report.py` (stdlib `smtplib` weekly report, self-only recipient) sent from the cloud by `.github/workflows/weekly-email.yml`

## What this project is about

The goal is to implement and backtest the trading strategy from Cohen &
Frazzini, "Economic Links and Predictable Returns" (this draft dated
2006-02-23; later published in the *Journal of Finance*, 2008). Details below
were verified against the PDF text (extracted via `pdftotext`), not recalled
from memory.

Core finding: due to investor limited attention, stock prices do not promptly
incorporate news about *economically linked* firms, producing cross-firm return
predictability. The links used are **customer-supplier** relationships. Under
SFAS 131 (SFAS 14 before 1997), a firm must disclose the identity of any
customer representing **more than 10% of total sales**; in the linked sample the
average customer accounts for **~20%** of the supplier's sales.

The strategy: each month, go long suppliers whose principal customer had the
most positive stock return last month and short those whose customer had the
worst, then rebalance monthly. The headline result is a long/short monthly alpha
of **over 150 basis points (>18% per year)**. Baseline portfolios are
**equal-weighted**; value-weighted variants are also reported. Risk adjustment
uses a **4-factor (Carhart) model**. The Coastcast / Callaway pair (Section I)
is the motivating worked example.

Key data facts for replication:
- **Universe / returns**: CRSP/Compustat, U.S. common stocks (CRSP share codes
  10 and 11).
- **Link data**: firms' principal customers from the **Compustat segment
  files**, mapped to the customer's CRSP `permno`.
- **Sample period**: customer-supplier data cover **1980–2004**.

## Pipeline shape

The stages are kept separable (data ingest → link mapping → signal → portfolio
→ performance) so each can be verified against the paper independently:

- **Link data**: the paper uses Compustat segment files (unavailable freely).
  We use a diversified LLM-extracted EDGAR link table (`universe_links.json`,
  via `elp/llm.py` / `elp/edgar.py`), with the free Cohen-Frazzini link file
  (`elp/cf_links.py`) as historical ground truth. The named-link limits are
  documented in `research/09`.
- **Returns data**: daily equity returns from Tiingo (`elp/tiingo.py`);
  keyless Yahoo (`elp/prices.py`) is a prototype only.
- **Signal construction**: prior-month customer return → supplier signal (`elp/signal.py`).
- **Portfolio / trade formation**: the live system is the dynamic per-trade
  engine (`elp/trades.py`); `elp/backtest.py` is the monthly cross-sectional
  long/short engine used for validation.

## Conventions

Follow the machine-global conventions in `~/.claude/CLAUDE.md` (concise commits
and push after meaningful changes, finance/quant framing, autonomy rules).
This project is deliberately **stdlib-only** — no third-party dependencies (not
even pandas/numpy). Keep it that way unless a dependency clearly earns its keep;
prefer bespoke stdlib code over adding a package.
