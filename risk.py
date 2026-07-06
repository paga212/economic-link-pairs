"""Daily Risk/Borrow pass: per open idea, deterministic borrow / earnings-window / liquidity
facts with a thin Opus note. Writes risk.json (consumed by digest.py / dashboard.py /
email_report.py). Fails SOFT so the pipeline never breaks.

Run: python3 risk.py
"""
import json

from elp.risk import build_risk

STATE, OUT = "paper_state.json", "risk.json"


def main() -> None:
    try:
        state = json.load(open(STATE))
    except FileNotFoundError:
        print(f"[risk] no {STATE} yet — run track.py first; skipping")
        return
    if not state.get("open"):
        print("[risk] no open ideas; skipping")
        return
    try:
        r = build_risk(state)
    except Exception as e:                    # no key / API / network -> fail soft
        print(f"[risk] skipped ({type(e).__name__}: {e})")
        return
    json.dump(r, open(OUT, "w"), indent=1)
    print(f"wrote {OUT} | {len(r['per_idea'])} ideas assessed | model={r['model_used']}")


if __name__ == "__main__":
    main()
