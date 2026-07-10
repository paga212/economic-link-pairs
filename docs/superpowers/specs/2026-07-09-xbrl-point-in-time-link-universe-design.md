# Point-in-time link universe from SEC XBRL, so the Cohen-Frazzini test has power

## Problem

`pairtest.py` returned `p = 0.828` on the live universe: the real customer-supplier wiring is
indistinguishable from a random rewiring. That result is uninformative, because after screening
the cross-section is **3 suppliers per formation month**. The test cannot reject anything.

An empirical power curve of the actual screen+placebo test (197 months, 10%/mo single-name vol,
`d` = loading of the supplier's month-M+1 return on the customer's month-M return):

```
   N | d=0.00 | d=0.05 | d=0.10 | d=0.20
   4 |    0%  |    0%  |   10%  |   15%     <- where we are today
  10 |    0%  |   50%  |   95%  |  100%
  25 |    0%  |   75%  |  100%  |  100%
  60 |   15%  |  100%  |  100%  |  100%
```

The paper's 150bp/month long/short implies `d ≈ 0.075` (a top-vs-bottom tercile spread in
customer returns is roughly 20%; `0.075 × 0.20 ≈ 1.5%`). **The target is ~25 suppliers per
formation month.** That is the stopping condition for this work.

## Why not the obvious sources

**The free Cohen-Frazzini historical link file is not usable, measured not assumed.** It keys
suppliers by CRSP permno and never names them; only the customer is named. Supplier names are
recoverable only for firms that were themselves someone's customer: **684 of 4,725**. Then
name→ticker for delisted 1980-2004 firms has no free source, and Tiingo is a modern-era feed
(536 US stocks with any history beginning in the 1980s). Three compounding gaps, two unfixable
for free.

**An LLM sweep of all 10-K filers** would catch text-only disclosures, but costs hours of EDGAR
crawling and thousands of LLM calls, is non-deterministic, and mostly duplicates what XBRL gives
free. Held in reserve if the sweep lands under ~25 suppliers.

## Source: SEC Financial Statement Data Sets

Measured facts, from `2024q1.zip` unless noted:

- `num.txt` carries a `segments` column back to at least **2013q1** (verified 2013q1, 2017q1,
  2021q1). Each quarterly zip is ~95-125MB.
- `srt:MajorCustomersAxis` appears as `MajorCustomers=<Member>`: **6,353 rows across 480
  filings** in 2024q1 (growing over time: 1,245 rows in 2013q1, 7,029 in 2021q1).
- Of 883 distinct members, 39 are anonymized by design (`CustomerA`, `CustomerOne`) and most of
  the rest are categories (`Other`, `ExternalCustomers`, `Intersegment`, `Residential`).
- Resolving members with the repo's **exact-norm** `resolve()` yields, over FY2024's four
  quarters: **53 links, 37 suppliers, 41 customers**, and they are recognisably real —
  `ICHR→LRCX`, `DAN→STLA`, `ATROB→BA`, `BNTX→PFE`, `CIEN→T`, `JAKK→TGT`, `EYE→WMT`.

A loose leading-token matcher inflated this to 371 links / 223 suppliers but produced obvious
garbage (`AEE→CMC`, `AEM→CUBB`). **Resolver precision is the project risk, not a detail.**
`research/09` already warned that false links pollute a fragile signal. A sloppy resolver
inflates N (raising apparent power) while injecting random pairs (biasing toward the null);
those effects point in opposite directions, so the placebo result would become uninterpretable.

Because every filing is dated, the links come out **point-in-time**, which retires the
look-ahead, static-link and survivorship biases the repo currently documents as known
limitations. That is why this is preferred over a fast current-snapshot build.

## Data flow

```
SEC FSDS quarterly zip (2013q1..2025q4)
   ├─ num.txt   rows where segments contains MajorCustomers=<Member>
   └─ sub.txt   adsh -> cik, fiscal period end
        ├─ supplier: cik    -> ticker   (SEC company_tickers.json, exact)
        └─ customer: Member -> ticker   (widened resolver, precision-gated)
        v
   xbrl_links.json   [{supplier, customer, fy_end, adsh}]   dated
        ├─ links_asof(month) -> what a trader could have known that month
        v
   long_short_returns -> screen -> placebo -> p-value + suppliers/month
```

## Components

**`elp/fsds.py` (new).** Downloads a quarterly zip to a temp path, streams `num.txt` and
`sub.txt` with stdlib `zipfile` + `csv`, yields `(cik, member, fy_end, value)` for
`MajorCustomers=` rows, then deletes the zip. Nothing over ~125MB is held or kept. Public
surface: `major_customers(quarter)` and `quarters(start, end)`.

**`elp/edgar.py` (extend).** `resolve_member(member, by_name, by_core)` widens the existing
`resolve()` under a precision gate: strip a trailing `Member`, split CamelCase, then try exact
norm, then spaceless, then a *core* index built by dropping corporate suffixes
(`inc corp corporation company co ltd llc plc holdings group`) and a leading `the`. A `CATEGORY`
frozenset rejects the measured non-company members before any match is attempted. Each widening
rule must pass a precision test; a rule that admits one bad link does not ship.

**`elp/pit.py` (new, small).** `links_asof(dated_links, months, lag=3, life=12)` →
`{formation_month: [(supplier, customer)]}`. A link disclosed for fiscal year ending `F` becomes
usable 3 months later (filing lag) and lapses 12 months after that (annual refresh). These two
constants are the module's only judgement calls; both are named and documented.

**`elp/backtest.py` (minimal change).** `long_short_returns` accepts `links` as either the
present `list[(s, c)]` or a `{month: [(s, c)]}` mapping, resolving the customer map per formation
month. Nothing else changes.

**`elp/pairtest.py` (extend).** `screen()` still runs on the *union* of pairs over full history,
because it must remain a pure function of `(links, returns)` for the placebo to stay valid.
`placebo()` permutes the union pairing and rebuilds the per-month table from the permutation, so
the null receives the same point-in-time treatment as the real links.

**`xbrl_build.py` (new driver)** writes `xbrl_links.json`. **`pairtest.py` (existing driver)**
grows a flag to read it.

## Reporting

Two numbers are added to `pairtest.py`'s output and neither may be swallowed:

- **suppliers per formation month** — the power number, judged against the ~25 target.
- **links dropped for missing Tiingo prices** — point-in-time links from 2013 include firms
  since delisted, and Tiingo's delisted coverage is thin. This count is a direct measurement of
  residual survivorship bias.

## Calibration gate

The power curve showed a **15% false-positive rate at N=60** where it should be 5%. On 20 trials
that is two standard errors, so probably noise, but it is not safe to assume.

**Before the real p-value is computed or reported**, re-run the `d = 0` column at the achieved N
with enough trials to pin the false-positive rate. If it is not near 5%, fix the test (more
placebo draws per trial) first. Deciding what "significant" means while we still have no stake in
the outcome is the same discipline as the placebo itself.

## Testing

Offline unit tests against a hand-built miniature zip (a few rows of `num.txt` / `sub.txt`),
following the existing suite's synthetic-data style:

- `major_customers` parses `segments` correctly and ignores non-customer axes.
- `resolve_member` accepts `AmazonComInc` and `Walmart`, and rejects every member in `CATEGORY`.
- `links_asof` respects the lag and the lapse exactly at their boundaries.
- `long_short_returns` returns identical results for a static list and for a mapping that repeats
  that list every month.

## Success criteria

1. `xbrl_links.json` holds dated links spanning 2013-2025, built deterministically, no LLM.
2. `pairtest.py` reports ≥ ~25 suppliers per formation month over a usable span.
3. The false-positive rate at the achieved N is confirmed near 5% before any p-value is quoted.
4. The p-value is reported plainly, whichever way it falls, with the price-drop count beside it.

## Out of scope

- The LLM sweep of text-only disclosures (option C). Reserved for if N lands under ~25.
- Retiring `trades.py` / `express.py` / `options.py` and the LLM overlays, and the lookahead-beta
  and in-sample-display bugs within them. Still pending the outcome of this work.
- Any change to the live paper-trade path. This is research.
