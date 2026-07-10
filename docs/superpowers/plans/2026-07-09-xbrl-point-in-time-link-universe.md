# Point-in-Time XBRL Link Universe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, point-in-time customer-supplier link universe from SEC XBRL so the Cohen-Frazzini test reaches ~25 suppliers per formation month and its p-value means something.

**Architecture:** Stream SEC Financial Statement Data Sets quarterly zips (2013q1-2025q4), pull rows tagged on `srt:MajorCustomersAxis`, resolve the filer CIK and the customer member string to tickers, and emit dated links keyed by the filing's public `filed` date. A small point-in-time layer turns dated links into a per-formation-month link table, which the existing monthly long/short engine and placebo test consume.

**Tech Stack:** Python 3, standard library only (`urllib`, `zipfile`, `csv`, `re`, `random`, `statistics`). Tiingo for prices. No pandas, no numpy, no LLM.

## Global Constraints

- **Stdlib only.** No third-party dependencies. This is a hard project rule (`CLAUDE.md`).
- **No LLM anywhere in this pipeline.** Link extraction must be deterministic and reproducible.
- **SEC requires a descriptive User-Agent** and caps traffic near 10 req/s. Reuse `elp.edgar.UA`.
- **Never quote a p-value before the calibration gate (Task 8) passes.**
- Every quarterly zip is ~95-125MB. Download to a temp path, parse, delete. Never commit one, never hold more than one at a time.
- `xbrl_links.json` IS committed (small, it is the reproducible artifact).
- Follow the existing test style: `tests/test_*.py`, `unittest`, `sys.path.insert` preamble, synthetic data, no network.
- Run the full suite with `python3 -m unittest discover -s tests`. It currently reports `Ran 164 tests` / `OK`.

---

## File Structure

| File | Responsibility |
|---|---|
| `elp/fsds.py` (new) | Fetch + stream one SEC quarterly zip; yield `MajorCustomers` rows. Knows nothing about tickers or links. |
| `elp/edgar.py` (modify) | Canonical CIK→ticker map; `CATEGORY` blocklist; `title_index()`; `resolve_member()`. |
| `xbrl_build.py` (new driver) | Sweep quarters, resolve both legs, write `xbrl_links.json`. |
| `elp/pit.py` (new) | `links_asof()` — dated links → `{formation month: [(supplier, customer)]}`. |
| `elp/backtest.py` (modify) | `long_short_returns` accepts a static link list *or* a per-month mapping. |
| `elp/pairtest.py` (modify) | `screen`/`placebo`/`screened_sharpe` handle a point-in-time link table. |
| `pairtest.py` (modify driver) | Read `xbrl_links.json`; report suppliers/month and price-drop count. |
| `calibrate.py` (new driver) | The calibration gate. Must run and pass before Task 8's p-value. |

## Facts established during design (do not re-derive)

- `num.txt` has a `segments` column back to at least 2013q1 (verified 2013q1, 2017q1, 2021q1).
- Customer axis renders as `MajorCustomers=<Member>` inside the semicolon-separated `segments`.
- `sub.txt` has `filed` (YYYYMMDD) — the date the disclosure became public. **Use it.** There is no need for a filing-lag constant.
- `norm()` in `elp/edgar.py` already strips corporate suffixes (`inc`, `corp`, `company`, `ltd`, `holdings`, `group`, `the`, ...). Do not add a second suffix stripper.
- `company_tickers.json` has multiple tickers per CIK (Ford: `F`, `F-PB`, `F-PC`, `F-PD`). Last-wins picks a preferred share. Canonicalize.
- Exact-norm resolution yields 43 customer members per quarter. Adding a CATEGORY blocklist + unique-prefix matching + ticker canonicalization yields **53**, and all 10 additions were verified correct by inspection (`Amazon→AMZN`, `Ford→F`, `BankOfMontreal→BMO`, `ASML→ASML`, `AppliedMaterials→AMAT`, `Jazz→JAZZ`, `Regal→RRX`, `Stellantis→STLA`, `ValeroEnergyCorporation→VLO`, `VertexPharmaceuticals→VRTX`).
- FY2024 with the exact matcher alone: 53 links, 37 suppliers, 41 customers.

---

### Task 1: `elp/fsds.py` — parse `MajorCustomers` rows from a quarterly zip

**Files:**
- Create: `elp/fsds.py`
- Test: `tests/test_fsds.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `quarters(start: str, end: str) -> list[str]` — e.g. `quarters("2013q1", "2013q3") == ["2013q1","2013q2","2013q3"]`
  - `major_customers(zip_path: str) -> list[dict]` — each dict: `{"cik": int, "member": str, "filed": date, "value": float | None}`
  - `fetch_quarter(quarter: str, dest: str) -> str` — downloads to `dest`, returns `dest`
  - `URL_TEMPLATE: str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fsds.py`:

```python
"""Offline unit tests for the SEC Financial Statement Data Sets reader (no network)."""
import io
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.fsds import major_customers, quarters  # noqa: E402

SUB = "\t".join(["adsh", "cik", "filed"]) + "\n" + \
      "0000-24-1\t320193\t20240201\n" + \
      "0000-24-2\t789019\t20240315\n"

# One customer row, one row on a different axis, one row whose adsh is unknown.
NUM = "\t".join(["adsh", "tag", "segments", "value"]) + "\n" + \
      "0000-24-1\tConcentrationRiskPercentage1\tConcentrationRiskByType=Cust;MajorCustomers=AppleIncMember;\t0.21\n" + \
      "0000-24-1\tConcentrationRiskPercentage1\tEquitySecuritiesByIndustry=SoftwareSector;\t0.13\n" + \
      "0000-24-2\tConcentrationRiskPercentage1\tMajorCustomers=CustomerAMember;\t\n" + \
      "0000-XX-9\tConcentrationRiskPercentage1\tMajorCustomers=GhostMember;\t0.99\n"


def _zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("sub.txt", SUB)
        z.writestr("num.txt", NUM)
    return path


class TestQuarters(unittest.TestCase):
    def test_enumerates_inclusive_range(self):
        self.assertEqual(quarters("2013q1", "2013q3"), ["2013q1", "2013q2", "2013q3"])

    def test_crosses_a_year_boundary(self):
        self.assertEqual(quarters("2013q4", "2014q2"), ["2013q4", "2014q1", "2014q2"])

    def test_single_quarter(self):
        self.assertEqual(quarters("2020q2", "2020q2"), ["2020q2"])


class TestMajorCustomers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.zip = _zip(os.path.join(self.tmp, "t.zip"))

    def test_extracts_only_major_customer_rows(self):
        rows = major_customers(self.zip)
        members = sorted(r["member"] for r in rows)
        self.assertEqual(members, ["AppleIncMember", "CustomerAMember"])

    def test_joins_cik_and_filed_date_from_sub(self):
        row = next(r for r in major_customers(self.zip) if r["member"] == "AppleIncMember")
        self.assertEqual(row["cik"], 320193)
        self.assertEqual(row["filed"], date(2024, 2, 1))
        self.assertAlmostEqual(row["value"], 0.21)

    def test_missing_value_becomes_none(self):
        row = next(r for r in major_customers(self.zip) if r["member"] == "CustomerAMember")
        self.assertIsNone(row["value"])

    def test_drops_rows_whose_filing_is_absent_from_sub(self):
        self.assertFalse([r for r in major_customers(self.zip) if r["member"] == "GhostMember"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_fsds -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'elp.fsds'`

- [ ] **Step 3: Write minimal implementation**

Create `elp/fsds.py`:

```python
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
        f.write(r.read())
    return dest


def _rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, "utf8"), delimiter="\t")


def major_customers(zip_path: str) -> list[dict]:
    """[{cik, member, filed, value}] for every MajorCustomers-tagged fact in the quarter."""
    z = zipfile.ZipFile(zip_path)
    sub = {r["adsh"]: r for r in _rows(z, "sub.txt")}
    out = []
    for r in _rows(z, "num.txt"):
        seg = r.get("segments") or ""
        if _AXIS not in seg:
            continue
        meta = sub.get(r["adsh"])
        if not meta:
            continue
        filed = meta["filed"]
        for part in seg.split(";"):
            if not part.startswith(_AXIS):
                continue
            raw = r.get("value") or ""
            out.append({"cik": int(meta["cik"]), "member": part[len(_AXIS):],
                        "filed": date(int(filed[:4]), int(filed[4:6]), int(filed[6:8])),
                        "value": float(raw) if raw else None})
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_fsds -v`
Expected: PASS, 7 tests, `OK`

- [ ] **Step 5: Commit**

```bash
git add elp/fsds.py tests/test_fsds.py
git commit -m "feat: stdlib reader for SEC XBRL major-customer disclosures"
```

---

### Task 2: `elp/edgar.py` — canonical tickers, CATEGORY blocklist, `resolve_member`

**Files:**
- Modify: `elp/edgar.py:40-59` (`load_ticker_map`, `resolve`)
- Test: `tests/test_edgar.py` (append; the file exists)

**Interfaces:**
- Consumes: `norm()`, `resolve()` (existing, unchanged behaviour).
- Produces:
  - `CATEGORY: frozenset[str]` — normalized non-company member keys
  - `title_index(by_cik: dict) -> dict[tuple[str, ...], set[str]]`
  - `resolve_member(member: str, by_name: dict, titles: dict) -> str | None`
  - `load_ticker_map()` keeps its `(by_cik, by_name)` shape; `by_cik[cik]["ticker"]` is now the canonical class (`F`, not `F-PD`).

**Why canonicalization is safe:** `phase_b_build.py`, `phase2a*.py` and `elp/linkcheck.py` all read `by_cik[cik]["ticker"]`. The shape is unchanged; they simply stop receiving preferred-share tickers. That is a strict improvement.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_edgar.py` (keep existing imports; add `CATEGORY, resolve_member, title_index` to the `elp.edgar` import line):

```python
class TestResolveMember(unittest.TestCase):
    """Customer members come from XBRL tags: 'AppleIncMember', 'CustomerAMember', 'OtherMember'."""

    def setUp(self):
        self.by_cik = {
            320193: {"ticker": "AAPL", "title": "Apple Inc."},
            1018724: {"ticker": "AMZN", "title": "AMAZON COM INC"},
            37996: {"ticker": "F", "title": "Ford Motor Co"},
            6951: {"ticker": "AMAT", "title": "APPLIED MATERIALS INC"},
            104169: {"ticker": "WMT", "title": "Walmart Inc."},
        }
        self.by_name = {}
        for row in self.by_cik.values():
            n = norm(row["title"])
            self.by_name.setdefault(n, row["ticker"])
            self.by_name.setdefault(n.replace(" ", ""), row["ticker"])
        self.titles = title_index(self.by_cik)

    def _r(self, m):
        return resolve_member(m, self.by_name, self.titles)

    def test_exact_match_after_stripping_member_suffix(self):
        self.assertEqual(self._r("WalmartInc"), "WMT")

    def test_exact_match_wins_before_any_widening(self):
        self.assertEqual(self._r("AppliedMaterials"), "AMAT")   # norm == 'applied materials'

    def test_unique_prefix_match_recovers_shortened_names(self):
        """'Amazon' is a strict prefix of the normalized title 'amazon com', and unique.
        'Ford' likewise prefixes 'ford motor'. Neither resolves by exact norm."""
        self.assertEqual(self._r("Amazon"), "AMZN")
        self.assertEqual(self._r("Ford"), "F")

    def test_rejects_anonymized_members(self):
        for m in ("CustomerAMember", "CustomerOneMember", "CustomerMember"):
            self.assertIsNone(self._r(m), m)

    def test_rejects_category_members(self):
        for m in ("OtherMember", "ExternalCustomersMember", "IntersegmentMember",
                  "ResidentialMember", "USGovernmentMember", "DistributionMember"):
            self.assertIsNone(self._r(m), m)

    def test_rejects_a_short_or_ambiguous_leading_token(self):
        self.assertIsNone(self._r("AbcMember"))          # leading token < 4 chars
        self.assertIsNone(self._r("ZzzzUnknownCoMember"))  # no title starts with it

    def test_ambiguous_prefix_is_rejected_not_guessed(self):
        by_cik = {1: {"ticker": "AAA", "title": "Delta Air Lines"},
                  2: {"ticker": "BBB", "title": "Delta Apparel"}}
        by_name = {norm(v["title"]): v["ticker"] for v in by_cik.values()}
        self.assertIsNone(resolve_member("Delta", by_name, title_index(by_cik)))


class TestCanonicalTicker(unittest.TestCase):
    def test_prefers_the_common_share_class(self):
        rows = {"0": {"cik_str": 37996, "ticker": "F-PD", "title": "Ford Motor Co"},
                "1": {"cik_str": 37996, "ticker": "F", "title": "Ford Motor Co"},
                "2": {"cik_str": 37996, "ticker": "F-PB", "title": "Ford Motor Co"}}
        self.assertEqual(_canonical(rows)[37996]["ticker"], "F")
```

Add to the import line at the top of `tests/test_edgar.py`:

```python
from elp.edgar import CATEGORY, _canonical, norm, resolve_member, title_index  # noqa: E402
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_edgar -v`
Expected: FAIL with `ImportError: cannot import name 'CATEGORY' from 'elp.edgar'`

- [ ] **Step 3: Write minimal implementation**

In `elp/edgar.py`, after `norm()` (line 37), insert:

```python
# XBRL customer members that are NOT companies. Filers tag categories and anonymized
# placeholders on the same axis as real names, so these must be rejected before any
# matching is attempted -- a fuzzy matcher will happily bind "Customers" to CUBB and
# "Business" to BFST. Keys are the member string with punctuation removed, lowercased,
# and a trailing "member" stripped. Measured against 2024q1 (883 distinct members).
CATEGORY = frozenset("""
other others customer customers client clients external externalcustomer externalcustomers
othercustomer othercustomers twocustomers intersegment intersegmentsales residential commercial
industrial wholesale retail government usgovernment nonusgovernment departmentofdefense consumer
business direct distribution transportation telecom military affiliated unaffiliated national
nationalaccounts thirdparty thirdpartynet toolanddie major domestic international foreign
segment segments product products service services corporate
customera customerb customerc customerd customere customerf
customerone customertwo customerthree customerfour customerfive customersix
""".split())


def _canonical(rows: dict) -> dict:
    """{cik: {'ticker','title'}} keeping ONE ticker per CIK. company_tickers.json lists every
    share class (Ford: F, F-PB, F-PC, F-PD) and last-wins would pick a preferred. Prefer a
    plain ticker, then the shortest, then alphabetical."""
    by_cik: dict[int, list] = {}
    for row in rows.values():
        by_cik.setdefault(int(row["cik_str"]), []).append((row["ticker"], row["title"]))
    out = {}
    for cik, tks in by_cik.items():
        tk, title = sorted(tks, key=lambda t: ("-" in t[0] or "." in t[0], len(t[0]), t[0]))[0]
        out[cik] = {"ticker": tk, "title": title}
    return out


def title_index(by_cik: dict) -> dict:
    """{normalized title token tuple: {ticker}} — the index unique-prefix matching walks."""
    idx: dict[tuple, set] = {}
    for row in by_cik.values():
        toks = tuple(norm(row["title"]).split())
        if toks:
            idx.setdefault(toks, set()).add(row["ticker"])
    return idx


def _member_key(member: str) -> str:
    return re.sub(r"member$", "", re.sub(r"[^a-z0-9]", "", member.lower()))


def _demember(member: str) -> str:
    """'AppleIncMember' -> 'Apple Inc'."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", re.sub(r"Member$", "", member))


def _prefix_unique(toks: tuple, titles: dict) -> str | None:
    """The single ticker whose normalized title STARTS WITH `toks`, or None if 0 or >1."""
    hits = {tk for t, tks in titles.items() if t[:len(toks)] == toks for tk in tks}
    return next(iter(hits)) if len(hits) == 1 else None


def resolve_member(member: str, by_name: dict, titles: dict) -> str | None:
    """Resolve an XBRL MajorCustomers member to a ticker, precision first.

    Three gates, in order: reject known non-companies; exact normalized match; then a
    UNIQUE prefix match (so 'Amazon' finds 'amazon com' but 'Delta' finds nothing, because
    Delta Air Lines and Delta Apparel both start with it). A leading token shorter than 4
    characters is rejected outright -- it matches too much.
    """
    if _member_key(member) in CATEGORY:
        return None
    name = _demember(member)
    tk = resolve(name, by_name)
    if tk:
        return tk
    toks = tuple(norm(name).split())
    if not toks or len(toks[0]) < 4:
        return None
    return _prefix_unique(toks, titles)
```

Then change `load_ticker_map()` to canonicalize. Replace its body's loop:

```python
def load_ticker_map() -> tuple[dict, dict]:
    """(by_cik: {int: {'ticker','title'}}, by_name: {norm(title): ticker}).

    One canonical ticker per CIK (the common share class, not a preferred). by_name is also
    indexed by the space-stripped norm so "Wal-Mart" (norm 'wal mart') matches "Walmart".
    Use resolve() for a name, resolve_member() for an XBRL member string.
    """
    by_cik = _canonical(json.loads(_get("https://www.sec.gov/files/company_tickers.json")))
    by_name = {}
    for row in by_cik.values():
        n = norm(row["title"])
        by_name.setdefault(n, row["ticker"])
        by_name.setdefault(n.replace(" ", ""), row["ticker"])
    return by_cik, by_name
```

Note: `_member_key` strips a trailing `member`, so `"CustomerAMember"` → `"customera"`, which is in `CATEGORY`. `"CustomerMember"` → `"customer"`, also in `CATEGORY`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_edgar -v`
Expected: PASS. Then `python3 -m unittest discover -s tests` → `OK` (no regression in `test_linkcheck.py`).

- [ ] **Step 5: Commit**

```bash
git add elp/edgar.py tests/test_edgar.py
git commit -m "feat: precision-gated resolution of XBRL customer members to tickers"
```

---

### Task 3: `xbrl_build.py` — sweep the quarters, write `xbrl_links.json`

**Files:**
- Create: `xbrl_build.py`
- No test file. This is a network driver; its logic (`fsds`, `edgar`) is already covered. Verified by running it.

**Interfaces:**
- Consumes: `elp.fsds.quarters/fetch_quarter/major_customers`; `elp.edgar.load_ticker_map/title_index/resolve_member`.
- Produces: `xbrl_links.json` — `[{"supplier": str, "customer": str, "filed": "YYYY-MM-DD", "pct": float | None}]`, sorted, deduplicated on `(supplier, customer, filed)`.

- [ ] **Step 1: Write the driver**

Create `xbrl_build.py`:

```python
"""Build the point-in-time customer-supplier link universe from SEC XBRL. No LLM.

Streams each quarterly Financial Statement Data Set, keeps facts tagged on
srt:MajorCustomersAxis, resolves the filer CIK to a supplier ticker and the member string to a
customer ticker, and writes dated links to xbrl_links.json. `filed` is the date the disclosure
became public, so the links are point-in-time by construction.

Zips are ~95-125MB each and are deleted after parsing. Run: python3 xbrl_build.py [start] [end]
"""
import json
import os
import sys
import tempfile

from elp.edgar import load_ticker_map, resolve_member, title_index
from elp.fsds import fetch_quarter, major_customers, quarters

OUT = "xbrl_links.json"


def main(start: str = "2013q1", end: str = "2025q4") -> None:
    by_cik, by_name = load_ticker_map()
    titles = title_index(by_cik)
    seen, links = set(), []
    for q in quarters(start, end):
        path = os.path.join(tempfile.gettempdir(), f"fsds_{q}.zip")
        try:
            fetch_quarter(q, path)
            rows = major_customers(path)
        except Exception as e:
            print(f"  warn {q}: {type(e).__name__} — quarter skipped")
            continue
        finally:
            if os.path.exists(path):
                os.remove(path)
        added = 0
        for r in rows:
            supplier = by_cik.get(r["cik"], {}).get("ticker")
            if not supplier:
                continue
            customer = resolve_member(r["member"], by_name, titles)
            if not customer or customer == supplier:
                continue
            key = (supplier, customer, r["filed"].isoformat())
            if key in seen:
                continue
            seen.add(key)
            links.append({"supplier": supplier, "customer": customer,
                          "filed": r["filed"].isoformat(), "pct": r["value"]})
            added += 1
        print(f"{q}: {len(rows):>6} tagged rows | +{added:>4} links | "
              f"total {len(links):>5} | suppliers {len({x['supplier'] for x in links}):>4}")
    links.sort(key=lambda x: (x["filed"], x["supplier"], x["customer"]))
    json.dump(links, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}: {len(links)} links, "
          f"{len({x['supplier'] for x in links})} suppliers, "
          f"{len({x['customer'] for x in links})} customers")


if __name__ == "__main__":
    main(*sys.argv[1:3])
```

- [ ] **Step 2: Smoke-test on two quarters**

Run: `python3 xbrl_build.py 2024q1 2024q2`
Expected: two progress lines, then a summary. `2024q1` should report roughly 6,300 tagged rows. Cumulative suppliers after `2024q2` should land near **34** (design measured 34 with the exact matcher; the widened resolver should add a few).

- [ ] **Step 3: Sanity-check the output by eye**

Run:
```bash
python3 -c "
import json,collections
d=json.load(open('xbrl_links.json'))
print(len(d),'links'); print(sorted({(x['supplier'],x['customer']) for x in d})[:20])"
```
Expected: recognisable links such as `('ICHR','LRCX')`, `('DAN','STLA')`, `('BNTX','PFE')`, `('EYE','WMT')`. **If you see pairs that make no economic sense, stop and fix `resolve_member` before continuing.** A false link is worse than a missing one.

- [ ] **Step 4: Run the full sweep** (long: ~50 quarters × ~100MB)

Run: `python3 xbrl_build.py 2013q1 2025q4`
Expected: a per-quarter line for each; final summary. Record the supplier count.

- [ ] **Step 5: Commit**

```bash
git add xbrl_build.py xbrl_links.json
git commit -m "feat: point-in-time link universe swept from SEC XBRL 2013-2025"
```

---

### Task 4: `elp/pit.py` — dated links → per-formation-month link table

**Files:**
- Create: `elp/pit.py`
- Test: `tests/test_pit.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `links_asof(dated, months, life=LIFE_MONTHS) -> dict[tuple[int,int], list[tuple[str,str]]]`
  where `dated` is `[{"supplier","customer","filed"}]` with `filed` an ISO string, and `months` is a list of `(year, month)` formation months. Also exports `LIFE_MONTHS: int`.

**Design note:** a link is live for formation months strictly after its `filed` month, and lapses `LIFE_MONTHS` months after `filed`. `LIFE_MONTHS = 15`, not 12: annual filings arrive roughly every 12 months and a 12-month life leaves gaps whenever a filing slips. 15 bridges the slip without letting a link persist through a full missed cycle. This constant is the module's only judgement call.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pit.py`:

```python
"""Offline unit tests for the point-in-time link table (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.pit import LIFE_MONTHS, links_asof  # noqa: E402


def _months(n, y0=2020, m0=1):
    out, y, m = [], y0, m0
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


LINK = [{"supplier": "S", "customer": "C", "filed": "2020-03-15"}]


class TestLinksAsof(unittest.TestCase):
    def test_link_is_absent_before_and_during_its_filing_month(self):
        t = links_asof(LINK, _months(6))
        self.assertEqual(t[(2020, 2)], [])
        self.assertEqual(t[(2020, 3)], [])     # not tradeable the month it was filed

    def test_link_is_live_the_month_after_filing(self):
        t = links_asof(LINK, _months(6))
        self.assertEqual(t[(2020, 4)], [("S", "C")])

    def test_link_lapses_exactly_life_months_after_filing(self):
        t = links_asof(LINK, _months(30))
        last = (2021, 3 + LIFE_MONTHS - 12)     # 2020-03 + 15 months = 2021-06
        self.assertEqual(t[last], [("S", "C")])
        y, m = last
        nxt = (y, m + 1) if m < 12 else (y + 1, 1)
        self.assertEqual(t[nxt], [])

    def test_a_refiling_extends_the_link(self):
        dated = LINK + [{"supplier": "S", "customer": "C", "filed": "2021-03-10"}]
        t = links_asof(dated, _months(30))
        self.assertEqual(t[(2022, 1)], [("S", "C")])     # covered by the 2021 filing

    def test_every_requested_month_is_a_key(self):
        t = links_asof(LINK, _months(6))
        self.assertEqual(sorted(t), sorted(_months(6)))

    def test_no_duplicate_pairs_within_a_month(self):
        dated = LINK + [{"supplier": "S", "customer": "C", "filed": "2020-03-20"}]
        self.assertEqual(links_asof(dated, _months(6))[(2020, 4)], [("S", "C")])

    def test_result_is_sorted_and_deterministic(self):
        dated = [{"supplier": "Z", "customer": "A", "filed": "2020-01-05"},
                 {"supplier": "A", "customer": "B", "filed": "2020-01-05"}]
        self.assertEqual(links_asof(dated, _months(3))[(2020, 2)], [("A", "B"), ("Z", "A")])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_pit -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'elp.pit'`

- [ ] **Step 3: Write minimal implementation**

Create `elp/pit.py`:

```python
"""Point-in-time link table: which links a trader could have known in each formation month.

SEC filings carry a `filed` date, so a disclosed customer link has an exact public birth date.
A link is usable from the month AFTER it was filed (you cannot trade on a filing during the
month it lands, without knowing the day) and lapses LIFE_MONTHS later.

LIFE_MONTHS = 15, not 12: annual filings arrive roughly every 12 months, and a 12-month life
opens a hole whenever a filing slips. 15 bridges a slip without letting a link survive a fully
missed cycle. This is the module's only judgement call. Pure stdlib.
"""
from __future__ import annotations

from datetime import date

LIFE_MONTHS = 15


def _idx(ym: tuple[int, int]) -> int:
    """Months since year 0, so month arithmetic and comparison are plain integers."""
    return ym[0] * 12 + (ym[1] - 1)


def links_asof(dated: list[dict], months: list[tuple[int, int]],
               life: int = LIFE_MONTHS) -> dict[tuple[int, int], list[tuple[str, str]]]:
    """{formation month: sorted unique [(supplier, customer)] live that month}."""
    spans = []
    for r in dated:
        f = date.fromisoformat(r["filed"])
        born = _idx((f.year, f.month))                  # live from born+1 .. born+life
        spans.append((born, r["supplier"], r["customer"]))
    out = {}
    for ym in months:
        i = _idx(ym)
        out[ym] = sorted({(s, c) for born, s, c in spans if born < i <= born + life})
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_pit -v`
Expected: PASS, 7 tests, `OK`

- [ ] **Step 5: Commit**

```bash
git add elp/pit.py tests/test_pit.py
git commit -m "feat: point-in-time link table keyed on the SEC filed date"
```

---

### Task 5: `elp/backtest.py` — accept a per-month link mapping

**Files:**
- Modify: `elp/backtest.py:26-61` (`long_short_returns`)
- Test: `tests/test_backtest.py` (append)

**Interfaces:**
- Consumes: `links_asof` output shape from Task 4.
- Produces: `long_short_returns(links, returns, cost_bps=0.0, side_frac=0.34)` where `links` is **either** `list[(s, c)]` (unchanged) **or** `dict[(y, m) -> list[(s, c)]]` keyed by **formation** month.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backtest.py`:

```python
class TestPointInTimeLinks(unittest.TestCase):
    def _returns(self):
        ms = _months(6)
        return {"S1": {m: 0.01 * i for i, m in enumerate(ms)},
                "S2": {m: -0.01 * i for i, m in enumerate(ms)},
                "C1": {m: 0.05 for m in ms},
                "C2": {m: -0.05 for m in ms}}

    def test_a_repeated_mapping_equals_the_static_list(self):
        """A per-month table that repeats the same links must reproduce the static result."""
        R = self._returns()
        static = [("S1", "C1"), ("S2", "C2")]
        pit = {m: list(static) for m in _months(6)}
        self.assertEqual(long_short_returns(static, R), long_short_returns(pit, R))

    def test_a_month_with_no_links_is_skipped(self):
        R = self._returns()
        pit = {m: [] for m in _months(6)}
        self.assertEqual(long_short_returns(pit, R), {})

    def test_links_absent_in_a_formation_month_do_not_trade_it(self):
        R = self._returns()
        ms = _months(6)
        pit = {m: ([("S1", "C1"), ("S2", "C2")] if i >= 3 else []) for i, m in enumerate(ms)}
        out = long_short_returns(pit, R)
        # formation month ms[i] drives holding month ms[i+1]
        self.assertNotIn(ms[1], out)
        self.assertIn(ms[4], out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_backtest -v`
Expected: FAIL — `long_short_returns` treats the dict as an iterable of keys and raises `ValueError: too many values to unpack` (or produces `{}`).

- [ ] **Step 3: Write minimal implementation**

In `elp/backtest.py`, replace the top of `long_short_returns` (the `cust_of` construction and `suppliers`/`holding_months` derivation) with a per-month lookup. The full replacement:

```python
def _cust_of(pairs: Links) -> dict[str, str]:
    """{supplier: principal customer}. First listed wins, matching the paper's 'principal'."""
    out: dict[str, str] = {}
    for s, c in pairs:
        out.setdefault(s, c)
    return out


def long_short_returns(links, returns: Returns,
                       cost_bps: float = 0.0, side_frac: float = 0.34) -> dict:
    """{(year, month): long-short holding-month return}. Formation = holding month - 1.

    `links` is either a static [(supplier, customer)] list, or a point-in-time
    {formation month: [(supplier, customer)]} mapping (see elp/pit.py) so each month
    ranks only the links disclosed by then.

    cost_bps: round-trip cost per leg in basis points, charged on both legs each month
    (full monthly turnover assumed). side_frac: fraction of names in each of long/short.
    """
    pit = isinstance(links, dict)
    if pit:
        holding_months = {_next(M) for M in links}
    else:
        cust_of = _cust_of(links)
        holding_months = set()
        for s in cust_of:
            holding_months |= set(returns.get(s, {}))

    out: dict = {}
    for H in sorted(holding_months):
        M = _prev(H)
        cust_of_M = _cust_of(links[M]) if pit else cust_of
        sig: dict[str, tuple[float, float]] = {}
        for s, c in cust_of_M.items():
            rc = returns.get(c, {}).get(M)   # customer prior-month return = signal
            rh = returns.get(s, {}).get(H)   # supplier holding-month return
            if rc is not None and rh is not None:
                sig[s] = (rc, rh)
        n = len(sig)
        if n < 2:
            continue
        ranked = sorted(sig, key=lambda s: (sig[s][0], s))  # ascending by customer prior return
        k = max(1, min(round(n * side_frac), n // 2))       # disjoint long/short slices
        shorts, longs = ranked[:k], ranked[-k:]
        ls = (mean(sig[s][1] for s in longs)
              - mean(sig[s][1] for s in shorts)
              - 2.0 * cost_bps / 1e4)
        out[H] = ls
    return out
```

Add `_next` beside the existing `_prev`:

```python
def _next(key: tuple[int, int]) -> tuple[int, int]:
    y, m = key
    return (y, m + 1) if m < 12 else (y + 1, 1)
```

Also update `signal_ranking` to use `_cust_of` instead of its inline loop (DRY; behaviour identical).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_backtest -v` then `python3 -m unittest discover -s tests`
Expected: both `OK`. The static path must be byte-identical — `test_a_repeated_mapping_equals_the_static_list` is the guard.

- [ ] **Step 5: Commit**

```bash
git add elp/backtest.py tests/test_backtest.py
git commit -m "feat: monthly engine accepts a point-in-time link table"
```

---

### Task 6: `elp/pairtest.py` — point-in-time screen and placebo

**Files:**
- Modify: `elp/pairtest.py` (`screen`, `screened_sharpe`, `placebo`, `suppliers_per_month`)
- Test: `tests/test_pairtest.py` (append)

**Interfaces:**
- Consumes: `elp.pit.links_asof`; `long_short_returns` accepting a mapping (Task 5).
- Produces:
  - `screen(links, returns, tradeable=None, min_months=MIN_MONTHS)` — **unchanged signature**, still takes the union of pairs.
  - `screened_sharpe(links, returns, cost_bps=0.0, tradeable=None, pit=None)`
  - `placebo(links, returns, n=1000, seed=0, cost_bps=0.0, tradeable=None, pit=None)`
  - `suppliers_per_month(links, returns, pit=None)`

  `pit` is `None` (static, present behaviour) or the `{month: [(s, c)]}` table. When `pit` is
  given, `links` is still the union of pairs — the screen runs on it, and the surviving pairs
  then *filter* the per-month table.

**Why the screen stays on the union:** `screen()` must remain a pure function of
`(links, returns)` so `placebo()` can apply the identical screen to a rewired universe. Screening
month-by-month would make the null and the real universe screened differently, and the p-value
would stop meaning anything. This is the load-bearing invariant of the whole battery.

**Keying asymmetry, deliberate:** `suppliers_per_month` returns keys that are *holding* months on
the static path (derived from supplier returns) and *formation* months on the PIT path (derived
from the table's own keys). Callers only ever consume `.values()`, so this is harmless — but
document it in the docstring rather than silently leaving a trap.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pairtest.py`:

```python
from elp.pairtest import screened_sharpe  # already imported; keep the existing line
from elp.pit import links_asof            # noqa: E402


class TestPointInTime(unittest.TestCase):
    def test_a_full_pit_table_matches_the_static_result(self):
        """If every month carries every link, PIT must equal static."""
        links, returns = _universe(n_pairs=6, lag_beta=0.6, seed=11)
        ms = _months(120)
        pit = {m: list(links) for m in ms}
        self.assertAlmostEqual(screened_sharpe(links, returns),
                               screened_sharpe(links, returns, pit=pit), places=9)

    def test_pit_filters_to_screened_pairs(self):
        """A pair dropped by screen() must not appear in any month the engine trades."""
        links, returns = _universe(n_pairs=6, lag_beta=0.6, seed=12)
        returns["CAH"] = returns.pop("C0")                    # make one customer pass-through
        links = [("S0", "CAH")] + links[1:]
        ms = _months(120)
        pit = {m: list(links) for m in ms}
        kept, _ = screen(links, returns)
        self.assertNotIn(("S0", "CAH"), kept)
        self.assertIsNotNone(screened_sharpe(links, returns, pit=pit))

    def test_placebo_is_deterministic_under_pit(self):
        links, returns = _universe(n_pairs=6, lag_beta=0.4, seed=13)
        pit = {m: list(links) for m in _months(120)}
        a = placebo(links, returns, n=30, seed=5, pit=pit)
        b = placebo(links, returns, n=30, seed=5, pit=pit)
        self.assertEqual(a, b)

    def test_suppliers_per_month_uses_the_pit_table(self):
        links, returns = _universe(n_pairs=4, n_months=40, seed=14)
        ms = _months(40)
        pit = {m: (list(links) if i >= 20 else []) for i, m in enumerate(ms)}
        counts = suppliers_per_month(links, returns, pit=pit)
        self.assertEqual(counts[ms[5]], 0)
        self.assertEqual(counts[ms[30]], 4)


class TestLinksAsofIntegration(unittest.TestCase):
    def test_dated_links_become_a_month_table_the_engine_accepts(self):
        links, returns = _universe(n_pairs=3, n_months=60, lag_beta=0.7, seed=15)
        dated = [{"supplier": s, "customer": c, "filed": "2015-01-10"} for s, c in links]
        pit = links_asof(dated, _months(60))
        self.assertIsNotNone(screened_sharpe(links, returns, pit=pit))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_pairtest -v`
Expected: FAIL with `TypeError: screened_sharpe() got an unexpected keyword argument 'pit'`

- [ ] **Step 3: Write minimal implementation**

In `elp/pairtest.py`:

```python
def _restrict(pit: dict, kept: list) -> dict:
    """Keep only screened pairs in each month's link list."""
    keep = set(kept)
    return {m: [p for p in pairs if p in keep] for m, pairs in pit.items()}


def _rewire_pit(pit: dict, mapping: dict) -> dict:
    """Apply a supplier->customer permutation to every month of a PIT table."""
    return {m: sorted({(s, mapping[s]) for s, _ in pairs if s in mapping})
            for m, pairs in pit.items()}
```

Change `screened_sharpe`:

```python
def screened_sharpe(links, returns, cost_bps: float = 0.0, tradeable=None, pit=None):
    """Annualized Sharpe of the long/short built from the *screened* links. None if the screen
    empties the universe or the series is degenerate. The one statistic the battery turns on;
    `placebo()` recomputes exactly this on each rewiring. When `pit` is given, the screened
    pairs filter the point-in-time table and each month trades only what was disclosed by then."""
    kept, _ = screen(links, returns, tradeable)
    if len(kept) < 2:                                  # long_short_returns needs a cross-section
        return None
    table = _restrict(pit, kept) if pit else kept
    perf = performance(long_short_returns(table, returns, cost_bps=cost_bps))
    if not perf.get("n"):
        return None
    sharpe = perf["sharpe"]
    return None if sharpe != sharpe else sharpe        # drop NaN (zero-vol series)
```

Change `placebo` to rewire the table too:

```python
def placebo(links, returns, n: int = 1000, seed: int = 0, cost_bps: float = 0.0,
            tradeable=None, pit=None) -> list[float]:
    """Sorted null distribution of `screened_sharpe` under random customer rewiring.

    Each draw permutes the customer column across the supplier column, preserving both name
    sets and every name's own return series, and destroying only the *pairing*. The same
    `screen()` then runs on the rewired universe, so the full-history lagged filter's
    selection bias applies to the null exactly as it applies to the real links. When `pit` is
    given, the rewiring is applied to every month of the table, so the null carries the same
    point-in-time structure as the real universe. Deterministic for a given seed.
    """
    rng = random.Random(seed)
    suppliers = [s for s, _ in links]
    customers = [c for _, c in links]
    out = []
    for _ in range(n):
        shuffled = customers[:]
        rng.shuffle(shuffled)
        rewired = [(s, c) for s, c in zip(suppliers, shuffled) if s != c]
        table = _rewire_pit(pit, dict(rewired)) if pit else None
        v = screened_sharpe(rewired, returns, cost_bps, tradeable, table)
        if v is not None:
            out.append(v)
    return sorted(out)
```

Change `suppliers_per_month`:

```python
def suppliers_per_month(links, returns, pit=None) -> dict:
    """{holding month: number of suppliers with both a signal and a return}. This is the
    cross-section the long/short is formed from, i.e. the test's power. A 4-name book cannot
    reject anything, and reading that as 'no edge' rather than 'no power' is the trap."""
    if pit:
        return {M: sum(1 for s, c in _cust_of(pairs).items()
                       if returns.get(c, {}).get(M) is not None
                       and returns.get(s, {}).get(_next(M)) is not None)
                for M, pairs in pit.items()}
    cust_of = _cust_of(links)
    months: set = set()
    for s in cust_of:
        months |= set(returns.get(s, {}))
    return {H: sum(1 for s, c in cust_of.items()
                   if returns.get(c, {}).get(_prev(H)) is not None
                   and returns.get(s, {}).get(H) is not None)
            for H in sorted(months)}
```

Update the import line at the top of `elp/pairtest.py`:

```python
from elp.backtest import _cust_of, _next, _prev, long_short_returns, performance
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_pairtest -v` then `python3 -m unittest discover -s tests`
Expected: both `OK`. `test_a_full_pit_table_matches_the_static_result` is the guard that the PIT path did not change the maths.

- [ ] **Step 5: Commit**

```bash
git add elp/pairtest.py tests/test_pairtest.py
git commit -m "feat: point-in-time screen and placebo"
```

---

### Task 7: `pairtest.py` — run on the XBRL universe, report power and price drops

**Files:**
- Modify: `pairtest.py`

**Interfaces:**
- Consumes: `xbrl_links.json`; `elp.pit.links_asof`; the Task 6 `pit=` parameters.
- Produces: printed report. No new module surface.

- [ ] **Step 1: Rewrite `pairtest.py`**

Replace the whole file with:

```python
"""Run the Cohen-Frazzini test battery on the link universe. Research only; trades nothing.

Signal = the paper's, unchanged: rank suppliers by their principal customer's prior-month
return, long the top slice, short the bottom, equal weight, hold one month (elp/backtest.py).

Prefers the point-in-time XBRL universe (xbrl_links.json, built by xbrl_build.py) and falls
back to the legacy static universe. Reads the placebo percentile as the headline -- but only
after calibrate.py has passed. Run: python3 pairtest.py
"""
import json
import os
from statistics import median

from elp.backtest import long_short_returns, performance
from elp.links import load_universe
from elp.pairtest import (PASS_THROUGH, _restrict, market_beta, null_summary, placebo,
                          placebo_pvalue, pooled_stats, screen, screened_sharpe,
                          suppliers_per_month)
from elp.pit import links_asof
from elp.prices import monthly_returns
from elp.tiingo import fetch_monthly

START = "2010-01-01"
PLACEBO_N = 1000
MARKET = "SPY"
LINKS_JSON = "xbrl_links.json"


def _load_dated():
    """(dated links, from_xbrl). The legacy static universe is modelled as filed long ago."""
    if os.path.exists(LINKS_JSON):
        return json.load(open(LINKS_JSON)), True
    return ([{"supplier": s, "customer": c, "filed": "2000-01-01"}
             for s, c, _ in load_universe()], False)


def main() -> None:
    dated, from_xbrl = _load_dated()
    pairs = sorted({(r["supplier"], r["customer"]) for r in dated})
    tickers = sorted({t for pair in pairs for t in pair} | {MARKET})

    returns, no_price = {}, []
    for t in tickers:
        try:
            returns[t] = monthly_returns(fetch_monthly(t, start=START))
        except Exception:
            no_price.append(t)
    links = [(s, c) for s, c in pairs if s in returns and c in returns]
    lost = len(pairs) - len(links)
    keep = set(links)
    dated = [r for r in dated if (r["supplier"], r["customer"]) in keep]

    src = "xbrl_links.json (point-in-time)" if from_xbrl else "static universe"
    print(f"\nuniverse: {src} | {len(links)} links, {len({s for s, _ in links})} suppliers")
    print(f"\nPRICE COVERAGE  {len(no_price)} of {len(tickers)} tickers had no Tiingo history; "
          f"{lost} of {len(pairs)} links dropped.")
    print("        Residual SURVIVORSHIP bias, measured rather than hidden: point-in-time links")
    print("        from 2013 include firms since delisted, which Tiingo covers thinly.")

    if len(links) < 2:
        print("\nfewer than 2 priced links: nothing to test.")
        return

    all_months = sorted({m for t in returns for m in returns[t]})
    pit = links_asof(dated, all_months) if from_xbrl else None

    # ---- screen -------------------------------------------------------------------------
    kept, rejected = screen(links, returns)
    print(f"\nSCREEN  (pass-through customers: {', '.join(sorted(PASS_THROUGH))})")
    reasons = {}
    for _pair, reason in rejected:
        reasons[reason] = reasons.get(reason, 0) + 1
    for reason, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  drop {n:>4}  {reason}")
    print(f"  keep {len(kept):>4}  links, {len({s for s, _ in kept})} suppliers")
    if len(kept) < 2:
        print("\nfewer than 2 links survive: no cross-section, nothing to test.")
        return

    table = _restrict(pit, kept) if pit else kept

    # ---- per-pair diagnostics (context, not a claim) ------------------------------------
    st = pooled_stats(kept, returns)
    print(f"\nPOOLED PAIR STATS  ({st['n_pairs']} pairs, diagnostic only)")
    print(f"  contemporaneous corr {st['contemp_corr']:+.3f}   (link is real if clearly > 0)")
    print(f"  lagged corr          {st['lagged_corr']:+.3f}   (biased up: pairs screened on it)")
    print(f"  up-minus-down        {st['up_minus_down'] * 100:+.2f}%/mo")

    # ---- portfolio ----------------------------------------------------------------------
    print("\nLONG/SHORT  (rank on prior-month customer return, hold 1 month)")
    for cost in (0.0, 10.0, 25.0):
        p = performance(long_short_returns(table, returns, cost_bps=cost))
        print(f"  {cost:>4.0f} bps | months {p['n']:>3} | ann_ret {p['ann_return'] * 100:>+6.1f}% "
              f"| ann_vol {p['ann_vol'] * 100:>5.1f}% | sharpe {p['sharpe']:>+5.2f} "
              f"| hit {p['hit_rate'] * 100:>4.1f}%")

    gross = long_short_returns(table, returns)
    print(f"  market beta vs {MARKET}: {market_beta(gross, returns[MARKET]):+.3f}  "
          "(a rank-formed spread should sit near zero)")

    # ---- power --------------------------------------------------------------------------
    counts = [v for v in suppliers_per_month(kept, returns, pit=table).values() if v]
    print(f"\nPOWER   suppliers per formation month: min {min(counts)}, "
          f"median {median(counts):.0f}, max {max(counts)}")
    print("        Target is ~25 (see docs/superpowers/specs/2026-07-09-...): below that the")
    print("        test cannot reject, and a null result means 'no power', not 'no edge'.")

    # ---- placebo: the headline ----------------------------------------------------------
    real = screened_sharpe(kept, returns, pit=table)
    null = placebo(links, returns, n=PLACEBO_N, pit=pit)
    ns = null_summary(null)
    print(f"\nPLACEBO  ({ns['n']}/{PLACEBO_N} rewirings survived the same screen)")
    print("  Each draw permutes the customer column across suppliers, preserving every name's")
    print("  own returns and destroying only the pairing, then applies the IDENTICAL screen.")
    print(f"  null sharpe: mean {ns['mean']:+.2f}  sd {ns['sd']:.2f}  "
          f"[p05 {ns['p05']:+.2f}, p95 {ns['p95']:+.2f}]")
    print(f"  real sharpe: {real:+.2f}")
    p = placebo_pvalue(real, null)
    print(f"\n  >>> p = {p:.3f}  (how often a RANDOM rewiring matches or beats the real links)")
    print("  >>> " + ("real links beat the null" if p <= 0.05 else
                      "the real wiring is indistinguishable from a random one"))
    print("\n  Quote this p-value ONLY if `python3 calibrate.py <N>` passed. The null mean is")
    print("  positive because the full-history lagged screen selects winners even out of noise;")
    print("  that bias is why the real Sharpe is compared to THIS null and never to zero.")


if __name__ == "__main__":
    main()
```

Note the two renames from the current file: the screen's rejected list is `rejected` (not
`dropped`), because `lost` now counts links dropped for missing prices. Do not reuse one name for
both — they are different failures and the report distinguishes them.

`screened_sharpe(kept, ...)` takes the already-screened list; `screen()` inside it is idempotent.
`placebo(links, ...)` takes the **unscreened** union, because the null must be screened itself.

Two edge cases to handle rather than crash on:
- `real` can be `None` if the screened universe degenerates. Guard before `f"{real:+.2f}"`.
- `null` can be empty if every rewiring fails the screen, and `null_summary([])` returns
  `{"n": 0}` with no `mean` key. Guard before reading `ns['mean']`. Print
  `"placebo produced no valid rewirings — the screen is too tight to test"` and return.

- [ ] **Step 2: Run it**

Run: `python3 pairtest.py`
Expected: the report, with `suppliers per formation month` now a median well above 3, plus the
new `PRICE COVERAGE` block. **Do not read the p-value yet.** Task 8 gates it.

- [ ] **Step 3: Commit**

```bash
git add pairtest.py
git commit -m "feat: run the battery on the point-in-time XBRL universe"
```

---

### Task 8: `calibrate.py` — the gate, then the answer

**Files:**
- Create: `calibrate.py`

**Interfaces:**
- Consumes: `elp.pairtest.screened_sharpe/placebo/placebo_pvalue`.
- Produces: printed false-positive rate. Nothing else in the codebase depends on it.

**Why this exists:** the design's power curve showed a **15% false-positive rate at N=60**, where
it must be 5%. On 20 trials that is two standard errors, so probably noise — but a p-value from a
mis-calibrated test is worthless, and we must decide what "significant" means before we have a
stake in the answer.

- [ ] **Step 1: Write the gate**

Create `calibrate.py`:

```python
"""Calibration gate: the false-positive rate of the screen+placebo test at the achieved N.

Under the null (no lead-lag), a 5%-level test must reject 5% of the time. If it rejects far more,
its p-value is not a p-value. Run this at the supplier count `pairtest.py` actually achieved,
BEFORE reading pairtest.py's p-value. Synthetic returns only; no network.

Run: python3 calibrate.py [n_suppliers] [trials] [placebo_draws]
"""
import random
import sys
from math import sqrt

from elp.pairtest import placebo, placebo_pvalue, screened_sharpe

MONTHS, SIGMA = 197, 0.10


def _months(n):
    out, y, m = [], 2010, 1
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


MS = _months(MONTHS)


def _null_universe(n, rng):
    """No lead-lag whatsoever: supplier returns are independent of the customer's."""
    links, R = [], {}
    for i in range(n):
        s, c = f"S{i}", f"C{i}"
        R[c] = {m: rng.gauss(0, SIGMA) for m in MS}
        R[s] = {m: rng.gauss(0, SIGMA) for m in MS}
        links.append((s, c))
    return links, R


def main(n: int = 37, trials: int = 200, draws: int = 400) -> None:
    rng = random.Random(0)
    hits = done = 0
    for t in range(trials):
        links, R = _null_universe(n, rng)
        real = screened_sharpe(links, R)
        if real is None:
            continue
        null = placebo(links, R, n=draws, seed=t)
        if not null:
            continue
        done += 1
        hits += placebo_pvalue(real, null) <= 0.05
    rate = hits / done if done else float("nan")
    se = sqrt(0.05 * 0.95 / done) if done else float("nan")
    print(f"N={n}  trials={done}  placebo draws={draws}")
    print(f"false-positive rate at alpha=0.05: {rate * 100:.1f}%  (target 5.0%, 1 SE = {se * 100:.1f}%)")
    ok = abs(rate - 0.05) <= 2 * se
    print("GATE PASSED — the p-value from pairtest.py is interpretable." if ok else
          "GATE FAILED — do NOT quote pairtest.py's p-value. Raise PLACEBO_N and re-run.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(*[int(a) for a in sys.argv[1:4]])
```

- [ ] **Step 2: Run the gate at the achieved N**

Run: `python3 calibrate.py <N from Task 7> 200 400`
Expected: `GATE PASSED`. If it fails, raise `PLACEBO_N` in `pairtest.py` (the discrete p-value's
resolution is `1/(draws+1)`; 400 draws resolves 0.25%) and re-run until it passes.

- [ ] **Step 3: Only now, read the answer**

Run: `python3 pairtest.py`
Record the p-value, the suppliers-per-month median, and the price-drop count.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`, with the new `test_fsds.py`, `test_pit.py`, and appended cases.

- [ ] **Step 5: Write up and commit**

Add a dated update block to the top of `NOTES.md` recording: the achieved supplier count, the
calibration result, the p-value, and the price-drop count. **Report the result plainly whichever
way it falls.** If the effect is absent on a properly powered test, that is the finding, and it
settles the open question in `NOTES.md` about whether to expand or stop.

```bash
git add calibrate.py NOTES.md
git commit -m "feat: calibration gate, and the powered answer"
```

---

## Notes for the implementer

- **A false link is worse than a missing one.** If Task 3's eyeball check surfaces a nonsense
  pair, stop and tighten `resolve_member`. Inflating N raises apparent power while injecting
  random pairs biases toward the null; the two effects fight, and the p-value stops meaning
  anything.
- **Never screen pairs month-by-month.** `screen()` runs on the union, always. The placebo's
  validity depends on the real universe and the null universe being screened identically.
- **The full sweep is ~50 downloads of ~100MB.** Run it once, commit `xbrl_links.json`, and never
  download again. The zips are deleted after parsing; do not cache them.
- Existing suite before this work: `Ran 164 tests` / `OK`. Never let it go red.
