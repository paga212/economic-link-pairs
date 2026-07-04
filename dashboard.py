"""Generate a self-contained static HTML dashboard for the paper trade.

Writes dashboard.html (no external assets, no deps) from paper_log.jsonl + realized
returns. Host it locally with:  python3 -m http.server 8787  ->  http://localhost:8787/dashboard.html

Run: python3 dashboard.py
"""
from datetime import datetime, timezone
from html import escape

from elp.paper import fetch_returns, load_entries, score

OUT = "dashboard.html"


def _pairs(names):
    return ", ".join(escape(s) for s, _ in names) or "—"


def build() -> None:
    entries = load_entries()
    returns = fetch_returns(entries) if entries else {}
    rows, t = score(entries, returns)
    latest = entries[-1] if entries else None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cur = "<p>No recommendation logged yet.</p>"
    if latest:
        f, h = latest["formation"], latest["holding"]
        cur = (f"<p class=sub>Formation {f[0]}-{f[1]:02d} &rarr; holding month "
               f"<b>{h[0]}-{h[1]:02d}</b></p>"
               f"<table><tr><th>Side</th><th>Suppliers (customer)</th></tr>"
               f"<tr><td class=long>LONG</td><td>{_long_cells(latest['longs'])}</td></tr>"
               f"<tr><td class=short>SHORT</td><td>{_long_cells(latest['shorts'])}</td></tr></table>")

    if t["n"]:
        stat = (f"cumulative L/S <b>{t['cum']*100:+.2f}%</b> &nbsp;|&nbsp; "
                f"avg <b>{t['avg']*100:+.2f}%</b>/mo &nbsp;|&nbsp; "
                f"hit <b>{t['hit']*100:.0f}%</b> &nbsp;|&nbsp; n={t['n']}")
        body = "".join(
            f"<tr><td>{r['holding'][0]}-{r['holding'][1]:02d}</td>"
            f"<td>{r['long']*100:+.2f}%</td><td>{r['short']*100:+.2f}%</td>"
            f"<td class='{'pos' if r['ls']>0 else 'neg'}'>{r['ls']*100:+.2f}%</td></tr>"
            for r in rows)
        matured = (f"<p>{stat}</p><table><tr><th>Holding</th><th>Long</th><th>Short</th>"
                   f"<th>L/S</th></tr>{body}</table>")
    else:
        matured = ("<p class=muted>No matured months yet — this is a forward test; "
                   "results appear as holding months complete.</p>")

    doc = f"""<!doctype html><html><head><meta charset=utf-8>
<title>Economic Link Pairs — Paper Trade</title>
<style>
 body{{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
 h1{{font-size:1.4rem;margin:0}} h2{{font-size:1.05rem;margin:1.6rem 0 .4rem;border-bottom:1px solid #eee;padding-bottom:.2rem}}
 .sub,.muted{{color:#666}} .muted{{font-style:italic}}
 table{{border-collapse:collapse;width:100%;margin:.3rem 0}} th,td{{text-align:left;padding:.35rem .6rem;border-bottom:1px solid #eee}}
 th{{color:#666;font-weight:600;font-size:.85rem}}
 .long{{color:#0a7a3f;font-weight:700}} .short{{color:#b02020;font-weight:700}}
 .pos{{color:#0a7a3f}} .neg{{color:#b02020}}
 .banner{{background:#fff8e1;border:1px solid #f0d98a;border-radius:6px;padding:.6rem .8rem;font-size:.9rem;color:#664d03}}
 footer{{color:#999;font-size:.8rem;margin-top:2rem}}
</style></head><body>
<h1>Economic Link Pairs — Paper Trade</h1>
<p class=sub>generated {now} · recommendations only, no execution</p>
<div class=banner><b>Forward paper-trade.</b> The evidence says this signal is likely weak
(decayed, thin/biased links, hard borrow). Judged against a pre-set kill rule. Metrics are
gross of costs for now.</div>
<h2>Current recommendation</h2>{cur}
<h2>Out-of-sample results</h2>{matured}
<footer>economic-link-pairs · Cohen &amp; Frazzini (2008) customer-supplier lead-lag</footer>
</body></html>"""
    open(OUT, "w").write(doc)
    print(f"wrote {OUT} ({len(rows)} matured, {'latest '+str(latest['holding']) if latest else 'no'} rec)")


def _long_cells(names):
    return ", ".join(f"{escape(s)} <span style='color:#999'>({escape(c)})</span>" for s, c in names) or "—"


if __name__ == "__main__":
    build()
