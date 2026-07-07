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

> **Update 2026-07-05 (News/Catalyst agent shipped — #9).**
> - **Phase-3 News/Catalyst agent.** Per open idea, three independent Opus source-agents judge
>   the customer catalyst + supplier confounding from separate evidence — Google News RSS
>   (`elp/news.py::google_rss`), Tiingo news (`tiingo_news`), and a web-search server tool
>   (`elp/llm.py::WEB_SEARCH_TOOL`, verified **enabled** on the API) — then a master `reconcile`
>   (Opus; deterministic `_majority` fallback) folds them into one verdict. `elp/catalyst.py` +
>   top-level `catalyst.py` → `catalyst.json`; wired into `run_paper.sh` **before** `digest.py`.
> - **Soft-derate only.** The digest down-ranks `none`/confounded ideas and the dashboard/email
>   show a per-idea flag (`catalyst: confirmed` / `⚠ no clear catalyst` / `⚠ confounded`). It does
>   NOT change which trades open/close — recommendations only. Numbers still come from state.
> - **Fail-soft everywhere:** dead source → `[]` → `unknown`; web-search 4xx → two-source
>   ensemble; no key → skip + exit 0. Built subagent-driven (7 TDD tasks); review caught two real
>   fail-soft holes (`_token()` outside try; unguarded source-agent LLM call), both fixed + regression-tested.
> - **Cost:** ~4 Opus calls/idea (3 agents + reconcile) + web-search fees ≈ a few dollars/day on
>   the 6-idea book. Batching all ideas into fewer calls is an easy later lever.
> - **Live smoke:** flagged `TTWO` confounded (its move is GTA VI, not the Apple link), confirmed
>   `ADSK`'s Synnex-earnings catalyst; the digest led with the one clean, unconfounded name.
> - **Tests: now 95** (`test_news`, `test_llm`, `test_catalyst`, `test_catalyst_entry` added). The
>   remaining Phase-3 agent is Risk/Borrow (borrow/ADV/earnings-window derate).

> **Update 2026-07-05 (Risk/Borrow agent shipped — #10; Phase-3 agent fleet complete).**
> - **Risk/Borrow agent (hybrid: code computes, LLM narrates).** Per open idea `elp/risk.py`
>   derives **borrow** (market-cap + ADV proxy on the short *stock* leg — a long idea's neutralizer;
>   short primaries are put-spreads → no borrow), **earnings-window** (Madsen: quarterly-cadence
>   estimate of next earnings + reported-since-entry), and a **liquidity** re-check; a thin Opus
>   `narrate` writes one sentence (no numbers). `risk.py` → `risk.json`; `run_paper.sh` runs
>   `catalyst → risk → digest`. The digest down-ranks hard-borrow / post-earnings / thin ideas; a
>   hard-borrow short is flagged **"short via options"** (NOT untradeable — primaries are already
>   put-spreads). New Tiingo helpers `fetch_marketcap` / `fetch_statement_dates`. Fail-soft
>   everywhere; recommendations only (never touches engine open/close).
> - Built subagent-driven (6 TDD tasks); reviews caught + fixed three fail-soft edge cases and a
>   borrow-proxy false-positive (**missing market-cap now defers to ADV**, not auto-"hard").
> - **Live smoke:** short-spread ideas → `borrow=na`; the two long ideas' short neutralizers
>   borrow-checked; the digest ranked ⚠ names low and even reasoned "borrow hard but irrelevant
>   here" for a long idea's hedge leg.
> - **Honest limits:** borrow is Grade-C (no free borrow feed); earnings is a cadence estimate, not
>   the announced date. Note: `risk.py` is fully fail-soft, so with no key/token it still writes a
>   `risk.json` of conservative labels (it does not "write nothing").
> - **Tests: now 113.** **Phase-3 agent fleet is COMPLETE** (Master digest, expression engine, link
>   validation, News/Catalyst, Risk/Borrow). The next remaining plan work is gated behind Phase 5.

> **Update 2026-07-06 (kill-rule bar + scorecard + trade-detail page; then paused on Phase 5).**
> - **Kill rule SET** (PLAN §11.8): pass = net Sharpe ≥ 0.5 **and** positive net expectancy **and**
>   ≥5 ideas/month, judged at the **later of** 12 months after paper_start (2026-07-04) and ≥30
>   closed OOS trades. Any miss → stop; the options overlay is cancelled, not "tried anyway."
> - **Kill-rule scorecard shipped** (`elp/killrule.py`, commit `a0c0aae`): pure render-time
>   PENDING/PASS/FAIL from `paper_state.json` (per-trade annualized Sharpe, expectancy, ideas/mo),
>   on the dashboard + email. Renders `[PENDING] month 0/12, 0/30` today; auto-delivers the verdict.
> - **Trade-detail page shipped** (`elp/tradeviz.py` + `tradeviz.py`, #11): `site/trades.html`
>   (linked from the dashboard) with per-trade inline-SVG leg charts + a combined return chart
>   (solid from entry + dashed hypothetical pre-entry) + sizing/P&L table; reuses `idea_return`/
>   `bear_put_spread`; runs in `run_paper.sh` after `dashboard.py`. **Tests: now 137.**
> - **Status: paused, by decision, on Phase 5.** Everything substantive that remains (Phase 6/7
>   options overlay, Track R) is gated on the forward test clearing the kill rule. Phase 5 has 0
>   closed OOS trades so far — it just needs time. **Watch:** the scorecard's gate progress
>   (months / closed-trade count) and, once trades close, whether net Sharpe/expectancy trend toward
>   the bar. Ungated follow-ups if wanted later: a precise **two-leg net-of-cost** model (track.py
>   currently charges cost single-leg) and a **Link Verification** QA agent (Phase 2 remainder).

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
- **Kill rule → SET 2026-07-05.** Pass = net Sharpe ≥ 0.5 **and** positive net expectancy
  (mean net return/trade > 0) **and** ≥5 ideas/month, judged at the **later of** 12 months after
  paper_start (2026-07-04) **and** ≥30 closed OOS trades. Any miss → stop; the options overlay is
  cancelled, not "tried anyway." Full definition in PLAN §11.8. Honest prior: evidence says the
  edge is likely weak, so FAIL is the base case to disprove.

### Known limitation
The `HIGHSIGNAL_LINKS` universe is Apple-supplier-heavy, so the long/short legs are
internally correlated (concentrated bets, not a diversified factor). Phase B LLM link
expansion is what diversifies it.

## Other open inputs (none blocking, all previously raised)
- Fable-5 key test (drop your Anthropic key in a file, same as Tiingo).
- ~~Success bar~~ → SET (see the "Kill rule → SET 2026-07-05" item above and PLAN §11.8).
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
