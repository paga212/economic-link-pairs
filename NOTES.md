# Session notes / handoff (2026-07-04)

Autonomous build session. Everything below is committed and pushed to `main`.
Full plan in `PLAN.md`; literature/data research in `research/`.

> **Update 2026-07-05 (correction to the record below).**
> - **Phase B shipped.** The LLM-diversified link universe is built and live (commits
>   `3ac4afa`, `95575c0`, `9b37f19`); the forward clock was restarted on it. Items in
>   "To make it a real forward test" that hinged on the Anthropic key for Phase B are done.
> - **The monthly `recommend.py`/`score.py` flow was superseded** by the daily dynamic
>   tracker `track.py` (→ `paper_state.json`). Those two files no longer exist; ignore the
>   monthly-cron snippet below and use `run_paper.sh` (already on a weekday-evening cron).
> - **Test count is now 26** (not 14); run `python3 -m unittest discover -s tests`.

> **Update 2026-07-05 (Phase 3 — Fable-5 Master digest shipped).**
> - Built the Master/Orchestrator daily digest: `elp/digest.py` + top-level `digest.py`,
>   wired into `run_paper.sh` between `track.py` and `dashboard.py`; `dashboard.py` renders a
>   "Daily read" section. It ranks the open paper trades and writes rationale/summary/watch;
>   **every number shown is pulled from `paper_state.json`, never the model** (PLAN.md §2).
>   Fails soft — no key / API error → dashboard keeps the numeric tables unchanged.
> - **Fable-5 IS reachable on the API** (`claude-fable-5` served directly; the Opus-4.8
>   auto-fallback in `elp/llm.complete_fallback` did not trigger). So the §5 "may not be
>   enabled" caveat is resolved: it works.
> - **Gotcha found + fixed:** Fable-5 runs **extended thinking by default** — thinking tokens
>   count against `max_tokens`. At `max_tokens=1500` thinking used ~1083 and the JSON
>   truncated (`stop_reason=max_tokens`). Raised the digest call to `max_tokens=4096`; unused
>   ceiling isn't billed. One digest ≈ ~2.5k output tokens (thinking + JSON) ≈ a few cents.
> - **Tests: now 34** (added `tests/test_digest.py`, fully offline — LLM monkeypatched). Run
>   `python3 -m unittest discover -s tests`. Verified live: `python3 digest.py` → model used
>   printed; `python3 dashboard.py` → digest section; every % cross-checked against state.
> - `digest.json` is generated + gitignored (like `dashboard.html`).

> **Update 2026-07-05 (later — expression engine, link validation, email delivery, storm recovery).**
> - **Expression engine shipped (#3).** Each signal is now a paired **two-legged long/short
>   idea** opened/closed as one unit: a primary leg on the supplier + a liquidity-chosen
>   **neutralizer** (counterpart supplier or ETF hedge). `elp/express.py` + `elp/liquidity.py`;
>   `paper_state.json` open rows now carry `expression` (`stock-pair`/`stock-hedge`) with
>   `primary`/`neutralizer` legs. #6 clamped the ETF-hedge beta to [0.3, 3.0].
> - **Link validation shipped (#5).** `elp/linkcheck.py` runs price-sanity + name↔ticker
>   checks on the Phase-B universe and quarantines bad links to `rejected_links.json`
>   (caught `NRP→ATGL` wrong-ticker via ambiguity, `MZTI→WMT` glitch-bar). Durable guard on
>   every Phase-B rebuild.
> - **Phase 4 delivery DONE — email shipped (#7).** `email_report.py` (stdlib `smtplib` +
>   Gmail App Password, self-only recipient, `EMAIL_DRYRUN` gate) renders the weekly report
>   from `paper_state.json`/`digest.json`. **Delivered from the cloud** by GitHub Actions
>   (`.github/workflows/weekly-email.yml`, Mondays 08:00 UTC) so it arrives even when the
>   basement PC is down — the storm on 2026-07-05 motivated this. Secret `GMAIL_APP_PASSWORD`
>   lives in repo Actions secrets; live send verified into the inbox. Basement cron is an
>   on-demand fallback. This resolves the "Delivery" and "macro-dashboard target" open items below.
> - **Storm / bad-reboot recovery.** A power loss corrupted the local `.git` (zero-length
>   objects); recovered cleanly from `origin` (working tree was never at risk). Repo healthy,
>   67 core tests green at recovery.
> - **Tests: now 71.** Run `python3 -m unittest discover -s tests`.

## Built and verified this session
- **Phase 0** (`phase0.py`, `elp/signal.py`, `elp/prices.py`): stdlib data spine +
  signal-direction check. Finding: on heavily-covered Apple/AMAT suppliers the same-month
  link is strong (~+0.5) but the one-month lag is absent — effect lives in *neglected*
  suppliers, as the paper says.
- **Phase 1** (`elp/backtest.py`, `elp/cf_links.py`, `phase1.py`): data-source-agnostic
  monthly long/short engine (verified by unit tests) + parser for the free Cohen-Frazzini
  link file (26k links, 1980-2005, permno-keyed).
- **Phase 2a** (`elp/edgar.py`, `phase2a*.py`): SEC EDGAR link extractor.
- **Data**: Tiingo wired as production prices (`elp/tiingo.py`), token validated.
- **Tests**: 26 offline unit tests, all pass (`python3 -m unittest discover -s tests`).
  *(Was 14 on 2026-07-04; the suite grew with Phase B/D.)*

## Key empirical findings
1. **Tiingo works but needs `permaTicker`.** Delisted spot-check: CELG retained through
   2019, but raw ticker "MON" returned a *different reused-ticker company* (recycling
   trap), LEHMQ empty. Phase 2 must key on permaTicker, not raw tickers. (`research/08`)
2. **Free-EDGAR named-link yield is ~4% and quality-adverse.** (`research/09`) Modern
   10-Ks usually file concentration as "one customer accounted for >10%" — unnamed,
   often unquantified. The customers that *are* named skew to retailers/distributors
   (Walmart, Target, Synnex = weak lead-lag signal); the high-signal tech links
   (Apple ↔ chip suppliers) are unnamed. So the named-only universe is thin AND biased.

## Phase C attempted (you chose "C then B") — hit a free-data wall
Tried to prove the effect on a historical backtest. Result (`research/10`):
- Rigorous free historical proof is **infeasible**: C-F links are permno-keyed and there
  is no free historical/delisted ticker map, so only **~28 of 26,339 links resolve** to
  current tickers (all survivors).
- Directional check on the 23 resolvable links (1998-2008): long/short **-2.5%/yr gross,
  Sharpe ~0** — no positive effect. Consistent with decay, but too thin/biased to be
  conclusive.

## Decision made: Option 1 — prove it forward (BUILT, dynamic per-trade)
Live daily tracker is running (superseded the earlier monthly recommender):
- **Strategy:** signal-triggered directional trades (customer trailing-21d return ±5%),
  dynamic exits — trailing stop (peak−5%, ratcheting) OR signal reversal (hysteresis),
  no time cap. LONG = cash stock; SHORT = **bear-put-spread** (no borrow, defined risk).
- `elp/trades.py` (engine) + `elp/options.py` (BS spread pricer, Grade-C proxied IV).
- `track.py` — daily: open trades (live stops) + OOS closed trades net of costs →
  `paper_state.json` (+ `paper_start.txt` = OOS boundary, **2026-07-04**).
- `dashboard.py` → `site/index.html`, served always-on at http://100.103.143.120:8787/.
- Cron: `0 22 * * 1-5` (weekday evenings) runs track → dashboard → serve → commit/push.

**Net-of-cost finding (in-sample, hand-set):** gross +0.89%/trade → NET −0.10%
with stock shorts, **+0.39% with bear-put-spread shorts** (kills borrow + caps the short
tail) → −0.11% at 2× costs. The spread number is a **Grade-C optimistic upper bound**
(flat IV, no skew, only 25bps stock-notional cost); real option bid-ask + put skew would
erode it. Needs real options data (Phase 6) to confirm.

### To make it a real forward test (remaining, mostly your calls)
- **~~Run it monthly.~~** *(Superseded 2026-07-05.)* The monthly `recommend.py`/`score.py`
  cron below no longer applies — those files were replaced by the daily dynamic tracker.
  The live cadence is `run_paper.sh` on `0 22 * * 1-5` (weekday evenings): it runs
  `track.py` → `dashboard.py` → `serve.sh`, then commits `paper_state.json` / `paper_start.txt`.
- **Anthropic key** → unlocks Phase B: LLM-inferred links from EDGAR to diversify the
  Apple-heavy universe (drop the key in a file like the Tiingo one).
- **~~Delivery~~ → DONE (2026-07-05).** Weekly email (`email_report.py`) to
  `pagrelletaumont@gmail.com`, sent from the cloud by GitHub Actions (basement-independent);
  dashboard served by `serve.sh`. See the 2026-07-05 update block above.
- **Kill rule** → set your bar (strawman ≥0.5 Sharpe / 5-10 ideas); if paper P&L doesn't
  clear it after N months, stop. Honest prior: the evidence says this is likely weak.

### Known limitation
The `HIGHSIGNAL_LINKS` universe is Apple-supplier-heavy, so the long/short legs are
internally correlated (concentrated bets, not a diversified factor). Phase B LLM link
expansion is what diversifies it.

## Other open inputs (none blocking, all previously raised)
- Fable-5 key test (drop your Anthropic key in a file, same as Tiingo).
- Success bar: net Sharpe + ideas/month (strawman: ≥0.5 Sharpe, 5-10 ideas).
- Is $10-20k **per idea** or **total** book?
- ~~Where does the `macro-dashboard` delivery target live?~~ Resolved: delivery is the weekly
  email to `pagrelletaumont@gmail.com` + the served dashboard (no separate `macro-dashboard`).

## How to run
```
python3 -m unittest discover -s tests   # 71 offline tests
python3 track.py                         # daily tick → paper_state.json (Tiingo token)
python3 digest.py                        # Fable-5 daily digest → digest.json (Anthropic key)
python3 dashboard.py                     # → site/index.html (served by serve.sh)
EMAIL_DRYRUN=1 python3 email_report.py   # render weekly email → email_report.eml (no send)
python3 linkcheck.py                     # validate the link universe → rejected_links.json
# earlier phase drivers: phase0.py, phase1.py, phase2a.py, phase2a_build.py 30
```
