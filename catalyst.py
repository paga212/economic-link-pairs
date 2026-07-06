"""Daily News/Catalyst pass: per open idea, an Opus 3-source ensemble judges the customer
catalyst + supplier confounding, reconciled by a master. Writes catalyst.json (consumed by
digest.py / dashboard.py / email_report.py). Fails SOFT so the pipeline never breaks.

Run: python3 catalyst.py
"""
import json

from elp.catalyst import build_catalyst

STATE, OUT = "paper_state.json", "catalyst.json"


def main() -> None:
    try:
        state = json.load(open(STATE))
    except FileNotFoundError:
        print(f"[catalyst] no {STATE} yet — run track.py first; skipping")
        return
    if not state.get("open"):
        print("[catalyst] no open ideas; skipping")
        return
    try:
        c = build_catalyst(state)
    except Exception as e:                    # no key / API / network -> fail soft
        print(f"[catalyst] skipped ({type(e).__name__}: {e})")
        return
    json.dump(c, open(OUT, "w"), indent=1)
    print(f"wrote {OUT} | {len(c['per_idea'])} ideas assessed | model={c['model_used']}")


if __name__ == "__main__":
    main()
