"""Generate the daily Master digest (Fable-5 -> Opus 4.8 fallback) from paper_state.json.

Reads paper_state.json + link notes, writes digest.json (rendered by dashboard.py).
Fails SOFT: missing state, no key, or an API/network error -> warn and exit 0, so the
track -> digest -> dashboard pipeline never breaks on the LLM step.

Run: python3 digest.py
"""
import json

from elp.digest import build_digest
from elp.links import load_universe

STATE, OUT = "paper_state.json", "digest.json"


def main() -> None:
    try:
        state = json.load(open(STATE))
    except FileNotFoundError:
        print(f"[digest] no {STATE} yet — run track.py first; skipping")
        return
    # Key by (supplier, customer): a supplier can name several customers, and the trade is on a
    # specific one — keying by supplier alone would paste a different customer's note beside it.
    notes = {(s, c): n for s, c, n in load_universe()}
    try:
        d = build_digest(state, notes)
    except Exception as e:                    # no key / API / network -> fail soft
        print(f"[digest] skipped ({type(e).__name__}: {e}) — dashboard keeps prior digest")
        return
    json.dump(d, open(OUT, "w"), indent=1)
    print(f"wrote {OUT} | model={d['model_used']} | ranked {len(d['ranked_open'])} open trades")


if __name__ == "__main__":
    main()
