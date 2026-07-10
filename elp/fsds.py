"""SEC Financial Statement Data Sets reader: named-customer disclosures, deterministically.

Each quarterly zip holds sub.txt (one row per filing) and num.txt (one row per tagged fact).
Customer concentration is tagged on srt:MajorCustomersAxis, which surfaces in num.txt's
`segments` column as `MajorCustomers=<Member>`. The member is the customer's name as the filer
chose to tag it -- often a real company ("AppleIncMember"), often anonymized ("CustomerAMember"),
often a category ("OtherMember"). Resolving that string is elp/edgar.py's job, not this module's.

`filed` in sub.txt is the date the disclosure became public, which is exactly the date a trader
could first have known the link. Point-in-time comes free; no filing-lag assumption is needed.

Zips are ~95-125MB. Stream them, then delete. Pure stdlib.
"""
from __future__ import annotations

import csv
import io
import shutil
import urllib.request
import zipfile
from datetime import date

from elp.edgar import UA

URL_TEMPLATE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{q}.zip"
_AXIS = "MajorCustomers="


def quarters(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYYqN' strings from `start` to `end`."""
    y0, q0 = int(start[:4]), int(start[5])
    y1, q1 = int(end[:4]), int(end[5])
    out = []
    while (y0, q0) <= (y1, q1):
        out.append(f"{y0}q{q0}")
        y0, q0 = (y0, q0 + 1) if q0 < 4 else (y0 + 1, 1)
    return out


def fetch_quarter(quarter: str, dest: str) -> str:
    """Download one quarterly zip to `dest`. The caller deletes it."""
    req = urllib.request.Request(URL_TEMPLATE.format(q=quarter), headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def _rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, "utf8"), delimiter="\t")


def major_customers(zip_path: str) -> list[dict]:
    """[{cik, member, filed, value, tag, uom}] for every MajorCustomers-tagged fact.

    `tag` and `uom` let a caller rank customers by disclosed USD revenue instead of by
    an arbitrary row order -- num.txt rows on this axis are overwhelmingly dollar revenue
    (RevenueFromContractWithCustomer*, Revenues), but also include non-revenue and
    non-USD facts that must not be conflated with it.
    """
    with zipfile.ZipFile(zip_path) as z:
        sub = {r["adsh"]: r for r in _rows(z, "sub.txt")}
        out = []
        skipped = 0
        for r in _rows(z, "num.txt"):
            seg = r.get("segments") or ""
            if _AXIS not in seg:
                continue
            meta = sub.get(r["adsh"])
            if not meta:
                continue
            try:
                filed = meta["filed"]
                for part in seg.split(";"):
                    if not part.startswith(_AXIS):
                        continue
                    # XBRL member identifiers (NCName) cannot contain ';' or '=', so split/startswith is safe.
                    raw = r.get("value") or ""
                    out.append({"cik": int(meta["cik"]), "member": part[len(_AXIS):],
                                "filed": date(int(filed[:4]), int(filed[4:6]), int(filed[6:8])),
                                "value": float(raw) if raw else None,
                                "tag": r.get("tag") or "",
                                "uom": r.get("uom") or ""})
            except (ValueError, KeyError, TypeError):
                skipped += 1
        if skipped:
            print(f"  warn {zip_path}: skipped {skipped} unparseable rows")
    return out
