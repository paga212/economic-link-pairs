# Position detail + Daily-read clarity — design

**Status:** design approved 2026-07-05 (brainstormed with Pierre).
**Builds on:** the expression engine (`elp/express.py` legs), `dashboard.py`, `email_report.py`,
and the Fable-5 digest (`elp/digest.py`).

## 1. Context and goal

Open-trade rows in the dashboard and email are too terse to act on. They show
`short put-spread 235/210p · debit 8.18 · 45DTE` with no share/contract count, no
indication of which strike is bought vs sold, and an unexplained `45DTE`. Separately,
the digest "Daily read" is one dense paragraph with no context, and its "Watch" list
overlaps confusingly with the ranked list. Goal: make each position self-explanatory and
the daily read clearer, with no new dependencies.

## 2. Leg detail — one shared formatter (`elp/express.py::describe_leg`)

`describe_leg(leg: dict, expression: str = "") -> str`, a pure function next to the leg
model, called by both `dashboard.py` and `email_report.py` so they cannot drift.

- **Stock leg:** `long 1,615 sh GILD @ $123.84 ($200k)`. Shares = `round(notional/entry_px)`,
  thousands-separated. A neutralizer is tagged `· pair` (`stock-pair`) or `· β-hedge` (`stock-hedge`).
- **Spread leg (primary short):** `bear put spread on PG (short): buy 147P / sell 133P ·
  ≈14 spreads · $3.60 debit · exp 45d · ≈$5.0k max risk`. Contracts = `round(notional/(100·spot))`,
  max risk = `contracts·debit·100`. `buy k_long / sell k_short` states the structure explicitly
  (long the higher-strike put, short the lower); `exp 45d` replaces the opaque `45DTE`. Contract
  count and max risk carry `≈` — the spread is a $200k-notional Grade-C model, not a sized order.

Both consumers wrap this text in their own markup (HTML-escaped in the dashboard and email
HTML part; raw in the email text part). `dashboard.py::_leg_str` and `email_report.py::_leg`
are removed in favour of it.

## 3. Daily read (dashboard)

- Add a one-line context header under the "Daily read" heading: *"An AI read of the open book,
  ordering and wording only. Every number shown is computed from the trades, not the model."*
- Reprompt the digest for **2-3 short declarative sentences** (not one paragraph); per-name
  rationales ≤ ~12 words, plain, grounded in the economic link, no numbers.

## 4. Merge "Watch" into the ranked list

Drop the separate `watch` list from `elp/digest.py` output and from the dashboard render.
The prompt instead tells the model: if a trade needs attention (thesis weakening / held long /
near stop), **prefix that name's rationale with "⚠ "** and say why briefly. One list, no overlap.
The email has no Watch section today, so it just inherits the crisper summary and richer legs.

## 5. Testing (offline, stdlib)

- `tests/test_express.py`: `describe_leg` on a long stock, a short bear-put-spread, and a
  β-hedge neutralizer — assert shares/contracts, `buy …P / sell …P`, `exp 45d`, `max risk`,
  and the `pair`/`β-hedge` tag.
- `tests/test_digest.py`: drop the `watch` assertions; assert the prompt requests attention-flagging
  and no separate watch list; ranked/number-preservation unchanged.
- `tests/test_email_report.py`: update spread-strike assertions to the new `buy …P / sell …P`
  form; keep `$60k`, expression, caveat, dashboard-link checks.

## 6. Out of scope
- Options-overlay sizing / real premium (still Grade-C, gated on Phase 5).
- Sector-specific hedges; any change to how trades are opened or scored.
