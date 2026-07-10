# Session notes / handoff (2026-07-04)

Autonomous build session. Everything below is committed and pushed to `main`.
Full plan in `PLAN.md`; literature/data research in `research/`.

> **Update 2026-07-10 — the universe was expanded, the test has power, and the effect is not there.**
>
> Follows the 2026-07-09 entry below, which found `p = 0.828` on a 3-supplier cross-section and
> could not tell "no edge" from "no power". The open decision was: expand the universe until the
> test has power, or stop. We expanded. See `xbrl_build.py`, `elp/fsds.py`, `elp/pit.py`,
> `calibrate.py`.
>
> **The universe.** SEC Financial Statement Data Sets, 2013q1 to 2025q4, 52 of 52 quarters parsed,
> zero skipped. Facts tagged on `srt:MajorCustomersAxis`, filer CIK resolved to the supplier
> ticker, the member string resolved to the customer ticker. Deterministic, stdlib only, no LLM.
> ```
> 938 dated links | 109 suppliers | 102 customers | filed 2013-01-07 .. 2025-12-12
> suppliers per formation month: median 40 (was 3)
> ```
> Links are **point-in-time**: `sub.txt` carries `filed`, the day the disclosure became public, so
> a link is live from the following month and lapses `LIFE_MONTHS = 15` later. A newer disclosure
> supersedes an older one, so a supplier holds exactly one customer in any month.
>
> **The gate, run before the answer was computed.**
> ```
> $ python3 calibrate.py 40 600 100 0
> false-positive rate at alpha=0.05: 4.8%  (target 5.0%, 1 SE = 0.89pp)
> CALIBRATED -- GATE PASSED
> ```
> The 15%-at-N=60 reading that motivated the gate was noise on 20 trials. An early 200-trial run
> printed 1.0% and FAILED; a pooled 600-trial run over three master seeds gave 5.33% +/- 0.89%.
> The gate now defaults to 600 trials, refuses to PASS below `MIN_DONE = 200`, takes a `seed`
> argument, and fails only an ANTI-conservative test. A conservative test cannot manufacture a
> false positive; it only loses power.
>
> **The answer.**
> ```
> $ python3 pairtest.py
> keep 42 links, 36 suppliers   (84 of 135 pairs dropped for lagged_corr <= 0)
>   0 bps | months 160 | ann_ret +28.8% | ann_vol 45.4% | sharpe +0.63 | hit 58.1%
>  25 bps |            | ann_ret +22.8% |               | sharpe +0.50 | hit 54.4%
>   market beta vs SPY: -0.094
> null sharpe (1000 rewirings, same screen): mean +0.44  sd 0.26  [p05 -0.01, p95 +0.87]
> real sharpe: +0.63
> >>> p = 0.234
> ```
> Stable across placebo seeds: p = 0.234, 0.239, 0.258, 0.242, 0.245 (mean 0.243).
>
> **A random rewiring of the same 135 links earns a mean Sharpe of +0.44.** Against zero, +28.8%
> annualized with a 58% hit rate and a -0.09 market beta looks like a discovery. Against the
> honest null it is a 77th-percentile draw. That gap is the entire value of the placebo.
>
> **And this time it is a real null, not an absence of power.** Injecting a known lead-lag loading
> `d` into the REAL returns (real vols, real point-in-time cross-section, same screen and placebo):
> ```
>       d  real sharpe  null mean       p   reject at 5%?
>   0.000         0.63       0.41   0.209   no      <- the observed data
>   0.050         0.86       0.43   0.047   YES
>   0.075         0.93       0.42   0.033   YES     <- the paper's ~150bp/mo implies d ~ 0.075
>   0.100         0.94       0.41   0.030   YES
>   0.150         1.20       0.40   0.007   YES
> ```
> At the paper's effect size the test detects it in 5 of 5 placebo seeds (p = 0.019 to 0.037).
> **We would have seen it. It is not there.**
>
> Note `pairtest.py`'s POWER line prints suppliers per formation month AFTER the screen (median 12)
> and compares it to a target (~25) derived BEFORE the screen. That comparison is apples to oranges.
> The injection test above is the real power measurement and supersedes it.
>
> ### What this result does and does not license
> - **Survivorship is understated by the report.** `PRICE COVERAGE` says 1 of 210 tickers lacked
>   Tiingo history, but we resolve each CIK through SEC's CURRENT ticker table, so firms delisted
>   before today never enter the universe at all. This inflates the +28.8%. It does NOT contaminate
>   the p-value: the placebo rewires within the same survivor set, lifting real and null together.
> - **Era.** 2013-2025, not the paper's 1980-2004. A null here is consistent with the effect having
>   been real and since arbitraged away. This test cannot separate that from its never existing.
> - **Tagging selection.** Only links whose customer is NAMED in XBRL survive; ~830 of 883 distinct
>   member strings per quarter are anonymized (`CustomerAMember`) or categorical (`Other`).
>   Single-token names (Ford, Amazon, Stellantis, ASML, Jazz) are excluded for precision, since they
>   produced every false link we found. That is a selection on filers' tagging habits.
> - **Ticker reuse.** A ticker can mean two companies over time (`B` was Barnes Group, now Barrick;
>   `GOLD` was Barrick, now Gold.com). Point-in-time links mostly defuse this, since a link only
>   trades in the 15 months after its filing.
> - **Principal customer.** Chosen by largest disclosed USD revenue per filing (678 groups), falling
>   back to alphabetical where no revenue row is rankable (260 groups). Sampling six quarters, only
>   1 of 135 filings took the fallback while actually having more than one customer to choose from.
>
> ### Bottom line
> The Cohen-Frazzini customer-supplier lead-lag does not survive an honest, powered, point-in-time
> test on free modern data. The deliberately-unfixed bugs in `trades.py` / `express.py` /
> `options.py` (lookahead beta, in-sample display) should now be resolved by RETIRING that code,
> not by fixing it. There is no edge here to trade.

> **Update 2026-07-09 — the placebo test says the link universe carries no edge.**
>
> Triggered by diving into the first dashboard pair, GILD vs CAH. That dive found the live
> system had drifted a long way from the paper, and that its reporting overstated what it knew.
> Decision: go back to the paper's actual claim (customer month-M return predicts supplier
> month-M+1 return) and test it honestly *before* rebuilding anything. See
> `elp/pairtest.py` + `python3 pairtest.py`.
>
> **Result (197 months, 2010-2026, live Tiingo):**
> ```
> real screened long/short sharpe  +0.11
> null (random rewiring, same screen)  mean +0.32  sd 0.23
> p = 0.828   -> the real wiring is indistinguishable from a random one
> ```
> The real customer-supplier wiring performs *worse* than the average random rewiring of the
> same tickers. Supporting evidence: of the 15 economically-admissible links, only **4 have a
> positive lagged correlation** (a real effect predicts clearly more than half), and 12 of 15
> have a negative up-minus-down spread.
>
> **But the test also has almost no power.** After screening, the cross-section is **3 suppliers
> per formation month** — a 1-long / 1-short book, 35.8% annualized vol, market beta −0.38. The
> paper ranked thousands of links. This universe cannot reject anything, so `p = 0.828` should
> be read as *"no evidence, and no ability to find any"* rather than *"the effect is dead."*
>
> **Why the placebo, and why the screen is inside it.** Pairs are screened on `lagged_corr > 0`
> over the same history the backtest runs on. Alone that is data snooping. The fix is not to
> drop the screen but to apply it *identically to the null*: each of the 1000 rewirings gets the
> same screen. 919/1000 survived it, and the null Sharpe mean is **+0.32, not zero** — the
> screen manufactures a positive Sharpe out of pure noise. That bias is why the real Sharpe is
> compared to this null and never to zero. `tests/test_pairtest.py` locks this in with a test
> that asserts the null mean is positive under i.i.d. noise, and a power check that a planted
> link still beats its own placebo (p ≤ 0.05).
>
> **What the GILD/CAH dive established** (all reproduced from live data, not read off JSON):
> - The trade was never a pair: `stock-hedge` = long $200k GILD, short $60k SPY. CAH is not in
>   the position. The +8.52% was unhedged GILD beta (GILD +8.94%, SPY +1.39%).
> - The `ENTER = ±5%` absolute threshold replaced the paper's *rank* with a *market bet*:
>   `corr(net long/short tilt of the book, SPY trailing 21d) = +0.709` over 2018-2026.
> - **Lookahead bug**, unfixed by design: `elp/express.py:79` sizes the hedge with `beta()` over
>   the *full* bar history (the 63 days ending at the **last bar**, not at entry). GILD's beta
>   was 0.5467 at entry and 0.0833 at the last bar (clamped to the 0.30 floor), so the hedge
>   shipped at $60k where entry-day beta implies $109k. `_px_asof` already fixed this bug class
>   for the neutralizer *price*; beta was missed. `is_tradeable` has the same lookahead.
> - Open ideas display in-sample return as if forward: GILD entered 2026-06-09, paper start is
>   2026-07-04, so +4.90% of that +8.52% predates the forward test.
>
> Those three are **deliberately not fixed** — `trades.py` / `express.py` / `options.py` and the
> LLM overlays are candidates for retirement, and polishing code we intend to delete is waste.
>
> **Pass-through links are now excluded on economics.** `PASS_THROUGH = {CAH, MCK, COR, ARW,
> SNX}`. SFAS 131 forces every pharma manufacturer to name the big three drug wholesalers as
> >10% customers; the disclosure is real but the economic link is not, because a distributor is
> a pass-through with no demand news to transmit. This screen runs before any return is read,
> so it cannot overfit. It drops 8 of 23 links, including GILD←CAH.
>
> **Also fixed (Phase 0, commit `27bcf41`).** "not enough overlapping price history to chart
> this trade" was a lie: a transient Tiingo failure on GILD was swallowed by `tradeviz.py`'s
> bare `except Exception: ohlc[t] = []` and reported as absent data. Nothing was logged.
> `elp/tiingo._fetch` now retries the transient classes (3 attempts, 1s/2s backoff; 4xx still
> raises immediately), the swallow now prints the ticker and exception type, and an empty leg
> series renders "price fetch failed for {ticker}".
>
> **Open decision.** Either expand the universe until the test has power, or conclude that a
> free-data replication of Cohen-Frazzini is not reachable and stop. The free C-F link file has
> 26,339 link-years across 4,725 suppliers, but only ~2 dozen resolve to current tickers
> (`research/09`), and those are survivors. Nothing should be rebuilt on the current 3-name
> cross-section.

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

> **Update 2026-07-07 (trade-detail charts fixed + heavily enhanced; docs synced).**
> - **Two real bug fixes.** (1) The trade-detail charts rendered blank: unquoted SVG
>   attributes before `/>` (e.g. `fill=none/>`) never self-closed, so each `<polyline>`
>   nested inside `<line>` (a non-container) and was not drawn — fixed by self-closing the
>   tags. (2) The neutralizer `entry_px` was taken from the last bar of full history instead
>   of the entry-day price (`build_idea` used `bars[cp][-1]`); now priced as-of the entry day,
>   which also corrects `idea_return` for the neutralizer leg. Both have regression tests.
> - **Chart enhancements** (`elp/tradeviz.py`): OHLC candlesticks for stock legs (new
>   `fetch_daily_ohlc`); the option (spread) leg keeps its distinctive blue mark line with the
>   underlying's candles grouped just above it (subtle blue accent group); labelled date x-axis;
>   nice-round horizontal gridlines with a y-value axis outside the plot (prices / percentages);
>   dated entry marker shown once on the top chart; last-bar date on the dashboard header;
>   explicit light/dark **toggle** (localStorage, replaces OS auto-detect) on both pages.
> - **Confirmed dynamic.** The trade set is not static: `track.py` re-simulates each tick and
>   `tradeviz.py`/`dashboard.py` rebuild from the current open list with fresh Tiingo data.
> - **Docs synced**: `CLAUDE.md` (Run/architecture/chain, `tradeviz`/`catalyst`/`risk`/`killrule`,
>   test count) and this log. **Tests: now 145.** Repo clean; `main` == `origin/main`. Stale local
>   branches `beta-clamp`, `link-validation`, `worktree-phase3-fable5-digest` are already
>   squash-merged into `main` (their deliverables are present) — safe to delete.

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
python3 -m unittest discover -s tests   # 231 offline tests
python3 xbrl_build.py                    # SEC XBRL sweep → xbrl_links.json (point-in-time links)
python3 calibrate.py 40 600 100 0        # calibration gate: run BEFORE quoting a p-value
python3 pairtest.py                      # C-F test battery: screen → pooled → L/S → placebo
python3 track.py                         # daily tick → paper_state.json (Tiingo token)
python3 catalyst.py                      # news/catalyst ensemble → catalyst.json (Anthropic key)
python3 risk.py                          # risk/borrow facts → risk.json (Anthropic key)
python3 digest.py                        # Fable-5 daily digest → digest.json (Anthropic key)
python3 dashboard.py                     # → site/index.html (served by serve.sh)
python3 tradeviz.py                      # per-trade detail charts → site/trades.html (Tiingo token)
EMAIL_DRYRUN=1 python3 email_report.py   # render weekly email → email_report.eml (no send)
python3 linkcheck.py                     # validate the link universe → rejected_links.json
# earlier phase drivers: phase0.py, phase1.py, phase2a.py, phase2a_build.py
```
