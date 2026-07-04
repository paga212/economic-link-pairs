"""Parse the free Cohen-Frazzini customer-supplier link file (Phase 2 groundwork).

Source: Frazzini's data library (pages.stern.nyu.edu/~afrazzin/data_library.htm),
"Customer Supplier Links.xlsx". Ground-truth links for 1980-2004. Firms are keyed by
CRSP **permno** (supplier) plus customer permno + name — so using this for a backtest
still needs a permno->ticker crosswalk and delisted price data (Phase 2 + real feed).

Pure stdlib xlsx reader (the file is a zip of XML). Not wired into the committed
tests because the data file is gitignored; run `python3 -m elp.cf_links` to summarize.
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DEFAULT = "data/cf_links.xlsx"


def _read_cells(path: str) -> list[list[str]]:
    z = zipfile.ZipFile(path)
    strings: list[str] = []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    for si in root.findall(f"{_NS}si"):
        strings.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
    sheet = next(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n))
    root = ET.fromstring(z.read(sheet))
    rows: list[list[str]] = []
    for r in root.findall(f".//{_NS}row"):
        cells = []
        for c in r.findall(f"{_NS}c"):
            v = c.find(f"{_NS}v")
            if v is None:
                cells.append("")
            else:
                cells.append(strings[int(v.text)] if c.get("t") == "s" else v.text)
        rows.append(cells)
    return rows


def load_cf_links(path: str = _DEFAULT) -> list[dict]:
    """Structured link records: supplier permno, customer permno/name, fiscal-year, sales."""
    rows = _read_cells(path)
    header = next(i for i, r in enumerate(rows)
                  if r and str(r[0]).strip().lower() == "permno")
    out: list[dict] = []
    for r in rows[header + 1:]:
        if len(r) < 4 or not r[0]:
            continue
        try:
            fy = str(r[3])
            fy_end = date(int(fy[:4]), int(fy[4:6]), int(fy[6:8])) if len(fy) == 8 else None
            total = float(r[4]) if len(r) > 4 and r[4] else None
            csale = float(r[5]) if len(r) > 5 and r[5] else None
            out.append({
                "supplier_permno": int(r[0]),
                "customer_name": r[1],
                "customer_permno": int(r[2]) if r[2] else None,
                "fy_end": fy_end,
                "total_sales": total,
                "customer_sales": csale,
                "concentration": (csale / total) if (total and csale) else None,
            })
        except (ValueError, IndexError):
            continue
    return out


def _summary(path: str = _DEFAULT) -> None:
    links = load_cf_links(path)
    suppliers = {r["supplier_permno"] for r in links}
    customers = {r["customer_permno"] for r in links if r["customer_permno"]}
    years = sorted({r["fy_end"].year for r in links if r["fy_end"]})
    from collections import Counter
    top = Counter(r["customer_name"] for r in links).most_common(8)
    print(f"C-F links: {len(links)} rows | {len(suppliers)} suppliers | "
          f"{len(customers)} customers | FY {years[0]}-{years[-1]}")
    print("top customers by link count:", ", ".join(f"{n} ({c})" for n, c in top))


if __name__ == "__main__":
    _summary()
