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

from elp.express import describe_leg
from elp.catalyst import catalyst_flag

TO = "pagrelletaumont@gmail.com"                 # sender AND sole recipient — never external
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587
STATE_FILE, DIGEST_FILE, EML_FILE = "paper_state.json", "digest.json", "email_report.eml"
DASHBOARD_URL = "http://100.103.143.120:8787/"
_PW_FILE = ".gmail_app_password"


def render(state: dict, digest: dict | None) -> tuple[str, str]:
    """(html, text) report. Every number comes from `state`, not an LLM."""
    opens = state.get("open", [])
    td = "padding:8px 10px;border-bottom:1px solid #eee"   # style body; each cell wraps it
    try:
        cat = json.load(open("catalyst.json")).get("per_idea", {})
    except (FileNotFoundError, ValueError):
        cat = {}
    rows, tlines = "", []
    for o in opens:
        direction = "LONG" if o["side"] > 0 else "SHORT"
        col = "#0a7a3f" if o["ret"] > 0 else "#b02020"
        p, n = describe_leg(o["primary"], o["expression"]), describe_leg(o["neutralizer"], o["expression"])
        flag = catalyst_flag(cat.get(f'{o["supplier"]}|{o["customer"]}'))
        rows += (f'<tr><td style="{td}"><b>{direction} {escape(o["supplier"])}</b>'
                 f'<div style="color:#888;font-size:12px">vs {escape(o["customer"])} · {o["days"]}d'
                 + (f' · {escape(flag)}' if flag else '') + '</div></td>'
                 f'<td style="{td};font-size:13px">{escape(o["expression"])}</td>'
                 f'<td style="{td};font-size:12px;color:#444">{escape(p)}<br>{escape(n)}</td>'
                 f'<td style="{td};color:{col};font-weight:600;text-align:right">{o["ret"]*100:+.1f}%</td></tr>')
        tlines.append(f'{direction} {o["supplier"]} vs {o["customer"]} [{o["expression"]}] '
                      f'{o["ret"]*100:+.1f}%' + (f' [{flag}]' if flag else '') + f' | {p}; {n}')

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
