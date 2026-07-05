# Weekly email report — design

**Status:** design approved 2026-07-05 (brainstormed with Pierre). Awaiting spec review → implementation plan.
**Builds on:** `paper_state.json` / `digest.json` (produced by `track.py` / `digest.py`) and the `run_paper.sh` weekday cron that keeps them fresh.

## 1. Context and goal

Deliver a **weekly email report** of the paper-trade to Pierre's own inbox. The
claude.ai Gmail MCP can only *draft* (no send tool) and is session-scoped (unusable
from a headless cron), so automation uses **`smtplib` + a Gmail App Password** —
stdlib, cron-safe, no new deps (PLAN.md §7 anticipated this). A sample was already
drafted via the MCP and the format approved.

**Decisions locked:** Monday 08:00 cadence; **auto-send to self** with a dry-run
flag; recipient hard-coded to `pagrelletaumont@gmail.com` (no external recipients).

## 2. Component

**New top-level `email_report.py`** (stdlib only: `smtplib`, `email.message.EmailMessage`,
`ssl`, `json`, `os`). One file, three responsibilities:

- `render(state: dict, digest: dict | None) -> tuple[str, str]` — build `(html, text)`
  from the state: header + caveat banner, the Fable-5 "Daily read" (if `digest` given),
  the two-legged open-ideas table (direction / expression / legs / net% / risk-cap),
  the OOS results block, and a link to the live dashboard. Pure, offline-testable.
- `_password() -> str` — read the Gmail App Password from `GMAIL_APP_PASSWORD` env or a
  gitignored `.gmail_app_password` file (mirrors `elp/tiingo.py::_token`). Raises a clear
  error if absent.
- `send(html, text, dryrun: bool)` — assemble a multipart `EmailMessage` (plain + html),
  From/To = `pagrelletaumont@gmail.com` (hard-coded constant `TO`), Subject dated. If
  `dryrun`, write the message to `email_report.eml` and print a one-line summary; else
  connect `smtp.gmail.com:587`, `starttls()` with a default SSL context, log in with
  `TO` + `_password()`, and `send_message`.

`main()`: load `paper_state.json` (+ `digest.json` if present), `render`, then `send`
with `dryrun = os.environ.get("EMAIL_DRYRUN") == "1"`. Missing `paper_state.json` →
print a notice and exit 0 (fail soft). No key + not dryrun → refuse with an instruction.

## 3. Data / rendering

Reads only `paper_state.json` (open ideas + OOS stats) and optional `digest.json`. The
two-legged idea rows format each leg — stock (`long/short TICK @ px ($Nk)`) or
bear-put-spread (`long/short put-spread K1/K2p · debit · DTE`) — and the neutralizer
notes `β-neutral`. No data refresh of its own: Monday's email reflects Friday's last
weekday tick. HTML uses **inline styles** (email-client-safe); a plain-text alternative
is always included.

## 4. Auth, secrets, delivery

- **App Password** in gitignored `.gmail_app_password` (add to `.gitignore`; the existing
  `*.key`/token rules don't already cover this name). Pierre generates it (requires
  2-Step Verification). A normal account password will not work with SMTP.
- **Transport:** `smtp.gmail.com:587` + STARTTLS (`ssl.create_default_context()`), auth
  with the App Password. Recipient hard-coded to `TO`; there is no recipient config.
- **Dry-run:** `EMAIL_DRYRUN=1` writes `email_report.eml` + prints, never opens a socket —
  the verify-before-live gate.

## 5. Cron (documented, NOT auto-enabled)

`0 8 * * 1 cd ~/projects/economic-link-pairs && python3 email_report.py >> email_report.log 2>&1`
Pierre adds this to crontab once the App Password is in place (same pattern as the paper
cron; the spec does not edit crontab).

## 5b. Cloud delivery (basement-independent) — GitHub Actions

The basement cron dies with the basement PC (the storm proved it). Primary delivery therefore
runs off-machine as a GitHub Actions scheduled workflow, `.github/workflows/weekly-email.yml`
(Mondays 08:00 UTC + `workflow_dispatch` for manual test). It checks out the repo and runs
`python3 email_report.py` (stdlib-only, so no install step) with `GMAIL_APP_PASSWORD` supplied
from repo Actions **secrets**. Because `email_report.py` reads only the *committed*
`paper_state.json`/`digest.json` and does no data refresh, the cloud job emails the last state
the basement pushed — so a dark basement still yields the last-known snapshot.

Belt-and-suspenders: GitHub Actions is the scheduled primary; the §5 basement cron is kept as an
**on-demand fallback** (run the one-liner if the cloud path ever fails) rather than a second
weekly schedule, to avoid a guaranteed weekly duplicate email. Scheduling both weekly would
require a shared git-marker dedupe (more fragile than it's worth for a self-email); deferred.

## 6. Testing

Offline unit tests (no network, no SMTP socket):
- `render()` on a synthetic 2-idea state (one stock-pair, one stock-hedge) → the HTML and
  text each contain both suppliers, their net %, the hedge/pair legs, the "recommendations
  only" caveat, and the dashboard link; a digest summary appears when `digest` is passed and
  is absent when `None`.
- Dry-run path: with `EMAIL_DRYRUN=1` and a stubbed/absent password, `send(..., dryrun=True)`
  writes `email_report.eml` and does **not** attempt a connection (assert the file is written;
  the SMTP path is not exercised).
- `_password()` reads env over file and raises a clear error when neither is set.
Live send is verified once by Pierre: `EMAIL_DRYRUN=1 python3 email_report.py` (inspect the
.eml), then a real run after the App Password is in place.

## 7. Blast radius (hot zone)

Live outbound send, but: recipient is **self only** (hard-coded, no external addresses),
gated behind `EMAIL_DRYRUN` and a required App Password, content is a read-only summary of
paper-trade state. Worst case: a duplicate or malformed self-email. No money, no trades, no
external recipients.

## 8. Out of scope
- Weekly-delta P&L / "what changed this week" logic (show current open ideas + cumulative OOS).
- Multiple/configurable recipients, CC/BCC, attachments.
- Reusing `dashboard.py`'s page renderer (email needs inline-styled, self-contained HTML;
  a small dedicated renderer is cleaner than forcing shared code).
- Auto-editing crontab, and any data refresh inside the email job.
