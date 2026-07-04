"""SEC EDGAR customer-supplier link extraction (Phase 2a, deterministic first pass).

Free, no API key. Uses EDGAR full-text search (discovery), the submissions API (a
filer's filings), and company_tickers.json (CIK<->ticker). Extracting the named
customer + concentration % from 10-K text is regex-based and imprecise BY DESIGN —
this is the first pass we then measure and later refine with an LLM. Pure stdlib.
SEC requires a descriptive User-Agent and caps traffic near 10 req/s.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "economic-link-pairs research (pagrelletaumont@gmail.com)"}
_SLEEP = 0.2  # be polite to SEC


def _get(url: str) -> bytes:
    time.sleep(_SLEEP)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
        return r.read()


_SUFFIX = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|"
    r"holdings?|group|technologies|technology|the)\b", re.I)


def norm(name: str) -> str:
    """Normalize a company name for matching (drop suffixes/punctuation/case)."""
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_ticker_map() -> tuple[dict, dict]:
    """(by_cik: {int: {'ticker','title'}}, by_name: {norm(title): ticker}).

    by_name is also indexed by the space-stripped norm so name variants like
    "Wal-Mart" (norm 'wal mart') match "Walmart" (norm 'walmart'). Use resolve().
    """
    data = json.loads(_get("https://www.sec.gov/files/company_tickers.json"))
    by_cik, by_name = {}, {}
    for row in data.values():
        by_cik[int(row["cik_str"])] = {"ticker": row["ticker"], "title": row["title"]}
        n = norm(row["title"])
        by_name.setdefault(n, row["ticker"])
        by_name.setdefault(n.replace(" ", ""), row["ticker"])
    return by_cik, by_name


def resolve(name: str, by_name: dict) -> str | None:
    """Resolve a customer name to a ticker: exact norm, then space-insensitive."""
    n = norm(name)
    return by_name.get(n) or by_name.get(n.replace(" ", ""))


def latest_10k(cik: int) -> tuple[str, str, str] | None:
    """(accession, primary_doc, filing_date) for the most recent 10-K, or None."""
    data = json.loads(_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    rec = data["filings"]["recent"]
    for form, acc, doc, dt in zip(rec["form"], rec["accessionNumber"],
                                  rec["primaryDocument"], rec["filingDate"]):
        if form == "10-K":
            return acc, doc, dt
    return None


def filing_text(cik: int, accession: str, primary_doc: str) -> str:
    """Fetch a filing's primary document and strip it to plain text."""
    acc = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{primary_doc}"
    raw = _get(url).decode("utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


_NAME = r"[A-Z][A-Za-z0-9&.,'\-]+(?:\s+[A-Z][A-Za-z0-9&.,'\-]+){0,4}"
_PCT = r"(\d{1,2}(?:\.\d+)?)\s*%"
_TAIL = r"of\s+(?:its\s+|our\s+|the\s+company'?s?\s+|consolidated\s+|total\s+|net\s+|gross\s+)*(?:net\s+)?(?:sales|revenues?)"
_PATTERNS = [
    re.compile(rf"({_NAME})\s+(?:accounted for|represented|comprised|generated)\s+"
               rf"(?:approximately\s+)?{_PCT}\s+{_TAIL}"),
    re.compile(rf"(?:approximately\s+)?{_PCT}\s+{_TAIL}\s+(?:were|was|are|is)?\s*"
               rf"(?:derived from|attributable to|to|from)\s+({_NAME})"),
    re.compile(rf"(?:sales|revenues?)\s+(?:to|from)\s+({_NAME})\s+"
               rf"(?:of\s+|represented\s+|accounted for\s+|were\s+|was\s+|totaled\s+|comprised\s+)"
               rf"(?:approximately\s+)?{_PCT}"),
]
_BADNAME = re.compile(
    r"^(The|This|These|Those|Our|Its|Net|Total|Sales|Revenue|Approximately|One|Two|"
    r"Three|No|Customer|Customers|A|An|In|For|Company|Sales|Fiscal)\b", re.I)


def extract_disclosures(text: str) -> list[dict]:
    """Best-effort [{customer, pct, snippet}] from customer-concentration language."""
    out, seen = [], set()
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            a, b = m.group(1), m.group(2)
            name, pct = (b, a) if re.match(r"\d", a) else (a, b)  # pattern 2 is (pct, name)
            name = name.strip(" .,")
            if len(name) < 3 or _BADNAME.match(name):
                continue
            key = (name.lower(), pct)
            if key in seen:
                continue
            seen.add(key)
            out.append({"customer": name, "pct": float(pct),
                        "snippet": text[max(0, m.start() - 30):m.end() + 30]})
    return out


_CONC = ("accounted for", "of net sales", "of net revenue", "of total revenue",
         "largest customer", "major customer", "one customer", "significant customer")


def concentration_snippets(text: str, window: int = 400, maxn: int = 4) -> list[str]:
    """Merged text passages around customer-concentration language (keeps LLM input small)."""
    low = text.lower()
    hits = []
    for p in _CONC:
        i = low.find(p)
        while i != -1 and len(hits) < 40:
            hits.append((max(0, i - window), min(len(text), i + window)))
            i = low.find(p, i + 1)
    hits.sort()
    merged: list[list[int]] = []
    for a, b in hits:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [text[a:b] for a, b in merged[:maxn]]


def full_text_search(query: str, forms: str = "10-K", frm: int = 0) -> list[dict]:
    """Discovery: filings whose full text contains `query` (exact phrase)."""
    q = urllib.parse.quote(f'"{query}"')
    data = json.loads(_get(
        f"https://efts.sec.gov/LATEST/search-index?q={q}&forms={forms}&from={frm}"))
    hits = []
    for h in data.get("hits", {}).get("hits", []):
        src = h.get("_source", {})
        acc, _, fn = h.get("_id", "").partition(":")
        ciks = src.get("ciks") or []
        hits.append({"cik": int(ciks[0]) if ciks else None,
                     "name": (src.get("display_names") or [""])[0],
                     "accession": acc, "filename": fn, "date": src.get("file_date")})
    return hits
