"""Validate universe_links.json in place: keep good links, quarantine bad ones to
rejected_links.json (with reasons). Run the one-time cleanup or any re-check.

Run: python3 linkcheck.py
"""
import json
from collections import Counter

from elp.linkcheck import validate_links

IN, REJ = "universe_links.json", "rejected_links.json"


def main() -> None:
    links = json.load(open(IN))
    good, rejected = validate_links(links)
    json.dump(good, open(IN, "w"), indent=1)
    json.dump(rejected, open(REJ, "w"), indent=1)
    reasons = dict(Counter(r["reason"] for r in rejected))
    print(f"kept {len(good)}/{len(links)} | rejected {len(rejected)}: {reasons}")
    for r in rejected:
        print(f"  drop {r['supplier']}->{r['customer']} ({r.get('customer_raw','')}): {r['reason']}")


if __name__ == "__main__":
    main()
