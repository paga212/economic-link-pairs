"""Generate the static HTML dashboard from paper_state.json (written by track.py).

Self-contained (no deps, no network). Writes site/index.html — served by serve.sh, so only
the site/ dir is exposed (never the repo/secrets). Host: python3 -m http.server 8787 -d site.

Run: python3 dashboard.py
"""
import json
import os
from html import escape

from elp.express import describe_leg
from elp.catalyst import catalyst_flag

OUT, STATE, DIGEST = "site/index.html", "paper_state.json", "digest.json"


def idea_row(o, catalyst=None):
    """One idea as an HTML row: net direction + both legs + expression + catalyst flag."""
    direction = "LONG" if o["side"] > 0 else "SHORT"
    cap = "$10k hard" if o.get("risk_cap") == "hard" else "~$10k stop (gap risk)"
    rcls = "pos" if o["ret"] > 0 else "neg"
    flag = catalyst_flag(catalyst)
    fhtml = f"<br><span class=sub>{escape(flag)}</span>" if flag else ""
    return (
        f"<tr><td><b>{direction} {escape(o['supplier'])}</b><br>"
        f"<span class=sub>vs {escape(o['customer'])}</span>{fhtml}</td>"
        f"<td>{escape(o['expression'])}</td>"
        f"<td class=sub>primary: {escape(describe_leg(o['primary'], o['expression']))}<br>"
        f"neutralizer: {escape(describe_leg(o['neutralizer'], o['expression']))}</td>"
        f"<td>{escape(o['entry'])}</td><td>{o['days']}d</td>"
        f"<td class={rcls}>{o['ret']*100:+.1f}%</td>"
        f"<td class=sub>{cap}</td></tr>")


def build() -> None:
    try:
        s = json.load(open(STATE))
    except FileNotFoundError:
        s = {"generated_utc": "—", "start": "—", "open": [], "closed": [], "stats": {}}

    def rcls(x):
        return "pos" if x > 0 else "neg"

    # Optional Master digest (Fable-5 / Opus). Additive: absent -> section omitted, tables
    # unchanged. Every number here comes from paper_state.json, never the model.
    digest_html = ""
    try:
        dg = json.load(open(DIGEST))
    except (FileNotFoundError, ValueError):
        dg = None
    if dg:
        ranked = "".join(
            f"<li><b>{escape(r['supplier'])}</b> &larr; {escape(r['customer'])} "
            f"<span class=sub>({escape(r.get('kind', 'LONG' if r.get('side', 0) > 0 else 'SHORT'))}, "
            f"<span class={rcls(r['ret'])}>{r['ret']*100:+.1f}%</span>)</span> — "
            f"{escape(r.get('rationale', '—'))}</li>"
            for r in dg.get("ranked_open", []))
        digest_html = (
            f"<h2>Daily read <span class=sub>({escape(str(dg.get('model_used', '—')))})</span></h2>"
            f"<p class=sub>An AI read of the open book &mdash; ordering and wording only; every "
            f"number shown is computed from the trades, not the model. A &#9888; flags a trade "
            f"needing attention.</p>"
            f"<p>{escape(dg.get('summary', ''))}</p>"
            + (f"<ol class=ranked>{ranked}</ol>" if ranked else "")
            + f"<p class=muted>{escape(dg.get('caveat', ''))}</p>")

    try:
        cat = json.load(open("catalyst.json")).get("per_idea", {})
    except (FileNotFoundError, ValueError):
        cat = {}
    open_rows = "".join(idea_row(o, cat.get(f'{o["supplier"]}|{o["customer"]}')) for o in s["open"]) or \
        "<tr><td colspan=7 class=muted>no open ideas</td></tr>"

    st = s.get("stats", {})
    if st.get("n"):
        cum = sum(c["ret_net"] for c in s["closed"])
        summary = (f"<p><b>{st['n']}</b> closed OOS trades &nbsp;|&nbsp; win "
                   f"<b>{st['win_rate']*100:.0f}%</b> &nbsp;|&nbsp; expectancy "
                   f"<b>{st['mean_ret']*100:+.2f}%</b>/trade &nbsp;|&nbsp; cumulative "
                   f"<b class={rcls(cum)}>{cum*100:+.1f}%</b> (net of costs)</p>")
        closed = "".join(
            f"<tr><td>{escape(c['entry'])}&rarr;{escape(c['exit'])}</td><td>{escape(c['kind'])}</td>"
            f"<td>{escape(c['supplier'])}</td><td>{c['days']}d</td><td>{escape(c['reason'])}</td>"
            f"<td class={rcls(c['ret_net'])}>{c['ret_net']*100:+.1f}%</td></tr>"
            for c in sorted(s["closed"], key=lambda c: c["entry"])[-25:])
        oos = (summary + "<table><tr><th>Entry&rarr;Exit</th><th>Side</th><th>Supplier</th>"
               f"<th>Held</th><th>Exit</th><th>Net</th></tr>{closed}</table>")
    else:
        oos = ("<p class=muted>No closed out-of-sample trades yet — the forward test just "
               "started. Results accrue as trades close.</p>")

    doc = f"""<!doctype html><html><head><meta charset=utf-8>
<title>Economic Link Pairs — Paper Trade</title>
<style>
 body{{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
 h1{{font-size:1.4rem;margin:0}} h2{{font-size:1.05rem;margin:1.6rem 0 .4rem;border-bottom:1px solid #eee;padding-bottom:.2rem}}
 .sub,.muted{{color:#666}} .muted{{font-style:italic}}
 table{{border-collapse:collapse;width:100%;margin:.3rem 0}} th,td{{text-align:left;padding:.35rem .6rem;border-bottom:1px solid #eee;font-size:.92rem}}
 th{{color:#666;font-weight:600;font-size:.82rem}}
 .detail td{{border-top:0;padding-top:0;font-size:.84rem}}
 .pos{{color:#0a7a3f;font-weight:600}} .neg{{color:#b02020;font-weight:600}}
 .banner{{background:#fff8e1;border:1px solid #f0d98a;border-radius:6px;padding:.6rem .8rem;font-size:.88rem;color:#664d03}}
 footer{{color:#999;font-size:.8rem;margin-top:2rem}}
</style></head><body>
<h1>Economic Link Pairs — Paper Trade</h1>
<p class=sub>generated {escape(str(s['generated_utc']))} · paper start {escape(str(s['start']))} · recommendations only, no execution</p>
<div class=banner><b>Forward out-of-sample paper-trade,</b> net of costs. Dynamic per-trade
management (trailing stop + signal exit); shorts as bear-put-spreads (Grade-C, optimistic).
The evidence prior is weak — judged against a pre-set 12-month kill rule.</div>
{digest_html}
<h2>Open trades</h2>
<table><tr><th>Idea</th><th>Expression</th><th>Legs</th><th>Since</th><th>Held</th><th>Net</th><th>Risk cap</th></tr>{open_rows}</table>
<h2>Out-of-sample results (net)</h2>{oos}
<footer>economic-link-pairs · Cohen &amp; Frazzini (2008) customer-supplier lead-lag</footer>
</body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(doc)
    print(f"wrote {OUT} ({len(s['open'])} open, {len(s['closed'])} OOS closed)")


if __name__ == "__main__":
    build()
