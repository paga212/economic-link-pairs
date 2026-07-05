# Weekly Email Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stdlib `email_report.py` that renders the paper-trade report from `paper_state.json`/`digest.json` and emails it from/to the user's own gmail via Gmail SMTP, with a dry-run safety gate.

**Architecture:** One top-level file, three units — `render(state, digest) -> (html, text)` (pure), `_password()` (secret loader mirroring `tiingo._token`), `send(html, text, dryrun)` (smtplib STARTTLS or `.eml` dry-run) — glued by `main()`. Offline tests cover `render` and the dry-run path; the live send is verified once by the user.

**Tech Stack:** Python 3 standard library only (`smtplib`, `email.message`, `ssl`, `json`, `os`). No new dependencies.

## Global Constraints

- **stdlib only** — no third-party deps.
- **Recipient hard-coded to `pierre@…`** (`TO = "pagrelletaumont@gmail.com"`) — no external recipients, no recipient config.
- **Numbers come from `paper_state.json`, never an LLM.**
- **Dry-run gate:** `EMAIL_DRYRUN=1` writes `email_report.eml` and never opens a socket.
- **Fail soft:** missing `paper_state.json` → notice + exit 0; missing password on a live run → refuse with instructions, do not crash.
- **Offline tests** — no network, no SMTP socket in the unit suite.
- **Reference:** `docs/superpowers/specs/2026-07-05-weekly-email-report-design.md`.

---

### Task 1: `render(state, digest) -> (html, text)`

**Files:**
- Create: `email_report.py` (module header, constants, `_leg`, `render`)
- Test: `tests/test_email_report.py`

**Interfaces:**
- Produces: `render(state: dict, digest: dict | None) -> tuple[str, str]` — email-safe inline-styled HTML and a plain-text alternative built from `state["open"]`, `state["stats"]`, and (optional) `digest["summary"]`.

- [ ] **Step 1: Write the failing test** (`tests/test_email_report.py`)

```python
"""Offline unit tests for the weekly email report (no network, no SMTP)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_report import render  # noqa: E402

STATE = {
    "generated_utc": "2026-07-05T16:00:00+00:00", "start": "2026-07-04",
    "open": [
        {"supplier": "GILD", "customer": "CAH", "side": 1, "expression": "stock-pair",
         "entry": "2026-06-25", "days": 7, "ret": 0.06, "stop": 0.01, "risk_cap": "soft",
         "primary": {"role": "primary", "ticker": "GILD", "direction": 1, "instrument": "stock",
                     "notional": 200000.0, "entry_px": 123.84},
         "neutralizer": {"role": "neutralizer", "ticker": "VC", "direction": -1,
                         "instrument": "stock", "notional": 200000.0, "entry_px": 102.45}},
        {"supplier": "PG", "customer": "WMT", "side": -1, "expression": "stock-hedge",
         "entry": "2026-07-01", "days": 1, "ret": -0.009, "stop": -0.05, "risk_cap": "soft",
         "primary": {"role": "primary", "ticker": "PG", "direction": -1, "instrument": "spread",
                     "notional": 200000.0, "entry_px": 147.4, "k_long": 147.0, "k_short": 133.0,
                     "debit": 3.60, "dte": 45},
         "neutralizer": {"role": "neutralizer", "ticker": "SPY", "direction": 1,
                         "instrument": "stock", "notional": 60000.0, "entry_px": 744.78}},
    ],
    "closed": [], "stats": {"n": 0, "win_rate": None, "mean_ret": None},
}


class TestRender(unittest.TestCase):
    def test_html_and_text_contain_the_ideas(self):
        html, text = render(STATE, None)
        for blob in (html, text):
            self.assertIn("GILD", blob)
            self.assertIn("PG", blob)
            self.assertIn("stock-hedge", blob)          # expression
            self.assertIn("147/133", blob)              # spread strikes
            self.assertIn("recommendations only", blob.lower())   # caveat
            self.assertIn("100.103.143.120:8787", blob)          # dashboard link
        self.assertIn("+6.0%", html)                    # net from state
        self.assertIn("$60k", html)                     # clamped hedge notional

    def test_digest_included_only_when_present(self):
        html_no, _ = render(STATE, None)
        self.assertNotIn("Daily read", html_no)
        html_yes, _ = render(STATE, {"model_used": "claude-fable-5", "summary": "Book looks fine."})
        self.assertIn("Daily read", html_yes)
        self.assertIn("Book looks fine.", html_yes)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_email_report -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'email_report'`

- [ ] **Step 3: Write minimal implementation** (`email_report.py`)

```python
"""Weekly email report of the paper-trade, sent from/to the user's own gmail via smtplib.

Reads paper_state.json (+ digest.json if present), renders an HTML+text report, and sends it
from/to TO over Gmail SMTP using a Gmail App Password (.gmail_app_password, gitignored).
EMAIL_DRYRUN=1 writes email_report.eml instead of sending. Recipient is hard-coded to TO —
no external recipients. Pure stdlib. Run: python3 email_report.py
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape

TO = "pagrelletaumont@gmail.com"                 # sender AND sole recipient — never external
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587
STATE_FILE, DIGEST_FILE, EML_FILE = "paper_state.json", "digest.json", "email_report.eml"
DASHBOARD_URL = "http://100.103.143.120:8787/"
_PW_FILE = ".gmail_app_password"


def _leg(l: dict) -> str:
    d = "long" if l["direction"] > 0 else "short"
    if l["instrument"] == "spread":
        return f'{d} put-spread {l["k_long"]:.0f}/{l["k_short"]:.0f}p · debit {l["debit"]:.2f} · {l["dte"]}DTE'
    tag = " · β-neutral" if l["role"] == "neutralizer" else ""
    return f'{d} {l["ticker"]} @ {l["entry_px"]:.2f} (${l["notional"]/1000:.0f}k{tag})'


def render(state: dict, digest: dict | None) -> tuple[str, str]:
    """(html, text) report. Every number comes from `state`, not an LLM."""
    opens = state.get("open", [])
    td = "padding:8px 10px;border-bottom:1px solid #eee"   # style body; each cell wraps it
    rows, tlines = "", []
    for o in opens:
        direction = "LONG" if o["side"] > 0 else "SHORT"
        col = "#0a7a3f" if o["ret"] > 0 else "#b02020"
        p, n = _leg(o["primary"]), _leg(o["neutralizer"])
        rows += (f'<tr><td style="{td}"><b>{direction} {escape(o["supplier"])}</b>'
                 f'<div style="color:#888;font-size:12px">vs {escape(o["customer"])} · {o["days"]}d</div></td>'
                 f'<td style="{td};font-size:13px">{escape(o["expression"])}</td>'
                 f'<td style="{td};font-size:12px;color:#444">{escape(p)}<br>{escape(n)}</td>'
                 f'<td style="{td};color:{col};font-weight:600;text-align:right">{o["ret"]*100:+.1f}%</td></tr>')
        tlines.append(f'{direction} {o["supplier"]} vs {o["customer"]} [{o["expression"]}] '
                      f'{o["ret"]*100:+.1f}% | {p}; {n}')

    st = state.get("stats", {}) or {}
    if st.get("n"):
        cum = sum(c["ret_net"] for c in state.get("closed", []))
        oos_t = (f'{st["n"]} closed OOS trades · win {st["win_rate"]*100:.0f}% · '
                 f'expectancy {st["mean_ret"]*100:+.2f}%/trade · cum {cum*100:+.1f}% (net)')
    else:
        oos_t = "No closed out-of-sample trades yet — the forward test just started."

    dg = ""
    if digest and digest.get("summary"):
        dg = (f'<h2 style="font-size:16px;margin:20px 0 6px">Daily read '
              f'<span style="color:#888;font-weight:400;font-size:13px">({escape(str(digest.get("model_used","")))})</span></h2>'
              f'<p style="color:#333">{escape(digest["summary"])}</p>')

    caveat = ("Forward out-of-sample paper-trade, net of costs. Each idea is a two-legged "
              "long/short unit risk-budgeted to ~$10k max drawdown. Recommendations only, no execution.")
    html = (f'<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:760px;'
            f'margin:0 auto;color:#1a1a1a;line-height:1.5">'
            f'<h1 style="font-size:20px;margin:0">Economic Link Pairs — Paper-Trade Weekly</h1>'
            f'<p style="color:#888;font-size:13px">generated {escape(str(state.get("generated_utc","")))} · '
            f'paper start {escape(str(state.get("start","")))} · <b>recommendations only, no execution</b></p>'
            f'<div style="background:#fff8e1;border:1px solid #f0d98a;border-radius:6px;padding:10px 12px;'
            f'font-size:13px;color:#664d03">{escape(caveat)}</div>{dg}'
            f'<h2 style="font-size:16px;margin:20px 0 6px">Open ideas ({len(opens)})</h2>'
            f'<table style="border-collapse:collapse;width:100%;font-size:14px">{rows}</table>'
            f'<h2 style="font-size:16px;margin:20px 0 6px">Out-of-sample results (net)</h2>'
            f'<p style="color:#555">{escape(oos_t)}</p>'
            f'<p style="margin-top:16px"><a href="{DASHBOARD_URL}" style="color:#1155cc">Open the live dashboard →</a></p>'
            f'</div>')

    text = ("Economic Link Pairs — Paper-Trade Weekly\n"
            f"generated {state.get('generated_utc','')} · paper start {state.get('start','')} · "
            "recommendations only, no execution\n\n"
            + caveat + "\n\n"
            + (f"Daily read ({digest.get('model_used','')}): {digest['summary']}\n\n"
               if digest and digest.get("summary") else "")
            + f"Open ideas ({len(opens)}):\n" + "\n".join(f"- {ln}" for ln in tlines)
            + f"\n\nOut-of-sample results: {oos_t}\n\nLive dashboard: {DASHBOARD_URL}\n")
    return html, text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_email_report -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add email_report.py tests/test_email_report.py
git commit -m "feat(email): render(state,digest) -> (html, text) weekly report"
```

---

### Task 2: `_password()` + `send(html, text, dryrun)`

**Files:**
- Modify: `email_report.py` (add `_password`, `send`)
- Test: `tests/test_email_report.py` (add a class)

**Interfaces:**
- Produces: `_password() -> str` (env `GMAIL_APP_PASSWORD` or `.gmail_app_password`/`~/.gmail_app_password` file; raises `RuntimeError` if absent). `send(html: str, text: str, dryrun: bool) -> None` — build the multipart message (From/To = `TO`, dated subject); dry-run writes `EML_FILE` + prints; live connects `SMTP_HOST:SMTP_PORT`, STARTTLS, logs in with `TO`+`_password()`, `send_message`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_email_report.py`)

```python
import email_report  # noqa: E402


class TestSend(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = os.path.join(os.path.dirname(__file__), "_emailtmp")
        os.makedirs(self._tmp, exist_ok=True)
        os.chdir(self._tmp)

    def tearDown(self):
        import shutil
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_dryrun_writes_eml_and_never_connects(self):
        # Poison smtplib so any socket attempt fails loudly; dry-run must not touch it.
        orig = email_report.smtplib.SMTP
        email_report.smtplib.SMTP = lambda *a, **k: (_ for _ in ()).throw(AssertionError("connected!"))
        try:
            email_report.send("<b>hi</b>", "hi", dryrun=True)
        finally:
            email_report.smtplib.SMTP = orig
        self.assertTrue(os.path.exists(email_report.EML_FILE))
        body = open(email_report.EML_FILE).read()
        self.assertIn(email_report.TO, body)
        self.assertIn("hi", body)

    def test_password_prefers_env_then_errors(self):
        os.environ["GMAIL_APP_PASSWORD"] = "abcd efgh ijkl mnop"
        try:
            self.assertEqual(email_report._password(), "abcd efgh ijkl mnop")
        finally:
            del os.environ["GMAIL_APP_PASSWORD"]
        # no env, no file in this tmp cwd, and force HOME miss -> RuntimeError
        home = os.environ.get("HOME")
        os.environ["HOME"] = self._tmp
        try:
            with self.assertRaises(RuntimeError):
                email_report._password()
        finally:
            if home is not None:
                os.environ["HOME"] = home
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_email_report -v`
Expected: FAIL — `AttributeError: module 'email_report' has no attribute 'send'`

- [ ] **Step 3: Write minimal implementation** (append to `email_report.py`)

```python
def _password() -> str:
    """Gmail App Password from GMAIL_APP_PASSWORD or a gitignored .gmail_app_password file."""
    raw = os.environ.get("GMAIL_APP_PASSWORD")
    if not raw:
        for p in (_PW_FILE, os.path.expanduser("~/.gmail_app_password")):
            if os.path.exists(p):
                raw = open(p).read()
                break
    if not raw:
        raise RuntimeError(
            "No Gmail App Password. Set GMAIL_APP_PASSWORD or create .gmail_app_password "
            "(Google Account → Security → 2-Step Verification → App passwords).")
    k = raw.strip()
    if "=" in k:                      # tolerate a pasted `export KEY='...'` line
        k = k.split("=", 1)[1]
    return k.strip().strip("'").strip('"').strip()


def _message(html: str, text: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"] = TO, TO
    msg["Subject"] = f"Economic Link Pairs — Paper-Trade Weekly ({datetime.now(timezone.utc).date().isoformat()})"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send(html: str, text: str, dryrun: bool) -> None:
    """Send the report from/to TO. dryrun -> write EML_FILE and print, never open a socket."""
    msg = _message(html, text)
    if dryrun:
        open(EML_FILE, "w").write(msg.as_string())
        print(f"[dryrun] wrote {EML_FILE} (no send). Subject: {msg['Subject']}")
        return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(TO, _password())
        s.send_message(msg)
    print(f"sent to {TO}: {msg['Subject']}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_email_report -v`
Expected: PASS (existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add email_report.py tests/test_email_report.py
git commit -m "feat(email): _password loader + send (STARTTLS or dry-run .eml)"
```

---

### Task 3: `main()` glue + gitignore

**Files:**
- Modify: `email_report.py` (add `main` + `__main__`)
- Modify: `.gitignore` (ignore the secret + the dry-run artifact)

**Interfaces:**
- Consumes: `render`, `send` (Tasks 1–2). `main()` loads `paper_state.json` (+ `digest.json` if present), renders, and sends with `dryrun = os.environ.get("EMAIL_DRYRUN") == "1"`. No `paper_state.json` → notice + return (exit 0).

- [ ] **Step 1: Add `main()`** (append to `email_report.py`)

```python
def main() -> None:
    try:
        state = json.load(open(STATE_FILE))
    except FileNotFoundError:
        print(f"no {STATE_FILE} — run track.py first; skipping email")
        return
    digest = json.load(open(DIGEST_FILE)) if os.path.exists(DIGEST_FILE) else None
    html, text = render(state, digest)
    dryrun = os.environ.get("EMAIL_DRYRUN") == "1"
    try:
        send(html, text, dryrun)
    except RuntimeError as e:            # missing password on a live run -> refuse, don't crash
        print(f"[email] not sent: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ignore the secret + dry-run artifact** (append to `.gitignore`)

```
# Weekly email report: Gmail App Password (secret) + dry-run artifact
.gmail_app_password
email_report.eml
```

- [ ] **Step 3: Verify — full suite + dry-run smoke**

Run: `python3 -m unittest discover -s tests` → all pass.
Run: `EMAIL_DRYRUN=1 python3 email_report.py` (in the repo root, with `paper_state.json` present) → prints `[dryrun] wrote email_report.eml`; open `email_report.eml` and confirm it contains the ideas + the dashboard link, and that `.gmail_app_password`/`email_report.eml` are git-ignored (`git status` clean of them).

- [ ] **Step 4: Commit**

```bash
git add email_report.py .gitignore
git commit -m "feat(email): main() glue + gitignore secret/dry-run artifact"
```

---

## Verification (controller / user)

1. Full offline suite green (`python3 -m unittest discover -s tests`).
2. **Dry-run** (controller): `EMAIL_DRYRUN=1 python3 email_report.py` → inspect `email_report.eml` renders correctly.
3. **Live send (user step):** create a Gmail App Password (Google Account → Security → 2-Step Verification → App passwords), put it in `.gmail_app_password`, run `python3 email_report.py`, confirm the email arrives.
4. **Enable weekly:** add `0 8 * * 1 cd ~/projects/economic-link-pairs && python3 email_report.py >> email_report.log 2>&1` to crontab.

## Self-Review

**Spec coverage:** §2 component (render/_password/send/main) → Tasks 1–3. §3 rendering (two-legged legs, inline styles, text alt, optional digest) → Task 1. §4 auth/dry-run/transport → Task 2 + Task 3 gitignore. §5 cron → Verification step 4 (documented, not auto-added). §6 tests (render + dry-run + _password) → Tasks 1–2. §7 hot-zone (self-only, dry-run gate) → `TO` constant + dry-run in Task 2.
**Placeholder scan:** none — every step has concrete code.
**Type consistency:** `render(state, digest) -> (html, text)` (Task 1) consumed by `send(html, text, dryrun)` (Task 2) and `main` (Task 3); `_password() -> str` used only inside `send`'s live branch; `EML_FILE`/`TO`/`STATE_FILE` constants referenced consistently across tasks and tests.

## Out of scope
- Weekly-delta P&L, multiple recipients, attachments, dashboard-renderer reuse, auto-editing crontab (all per spec §8).
