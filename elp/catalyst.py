"""News/Catalyst agent (Phase 3): per open idea, three independent Opus source-agents judge the
customer catalyst + supplier confounding from RSS / Tiingo / web-search evidence; a master
reconciles them. Code fetches; the LLM only reasons — no agent emits a number. Fail-soft.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from elp.llm import AnthropicError, WEB_SEARCH_TOOL, complete, parse_json
from elp.news import google_rss, tiingo_news

OPUS = "claude-opus-4-8"

_SRC_SYS = (
    "You are a News/Catalyst analyst for a customer-supplier lead-lag trading system (a "
    "supplier's stock is slow to reflect news about its principal customer). Judge two things "
    "and return ONLY a JSON object: (1) did a GENUINE customer information event (earnings, "
    "guidance, a major deal/contract, product, regulatory) plausibly drive the customer's recent "
    "move; (2) is there SUPPLIER-specific news that already explains the supplier's move (a "
    "confound). Never invent events not supported by the evidence.")

_REC_SYS = (
    "You reconcile three independent News/Catalyst verdicts into one. Weigh agreement, recency, "
    "and relevance; ignore 'unknown' verdicts. Return ONLY a JSON object. Never invent facts.")

_SCHEMA = (
    'Return JSON: {"customer_catalyst":"confirmed|weak|none","catalyst_note":"<=15 words",'
    '"confounding_supplier_news":"yes|no","confounding_note":"<=15 words"}. '
    'If the evidence is empty or irrelevant, use "none"/"no" and say so.')


def _headlines_block(items: list, n: int = 8) -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  - {it['title']} ({it.get('date', '')})" for it in items[:n])


def _unknown(source: str, why: str) -> dict:
    return {"source": source, "customer_catalyst": "unknown", "catalyst_note": why,
            "confounding_supplier_news": "unknown", "confounding_note": why}


def _verdict_from(source: str, data: dict) -> dict:
    data = data if isinstance(data, dict) else {}
    return {"source": source,
            "customer_catalyst": data.get("customer_catalyst", "unknown"),
            "catalyst_note": str(data.get("catalyst_note", "")).strip(),
            "confounding_supplier_news": data.get("confounding_supplier_news", "unknown"),
            "confounding_note": str(data.get("confounding_note", "")).strip()}


def _source_verdict(source: str, cust: str, sup: str, cust_items: list, sup_items: list) -> dict:
    """One Opus call judging catalyst + confounding from passed-in headlines. No evidence -> skip
    the call and return 'unknown' (saves cost)."""
    if not cust_items and not sup_items:
        return _unknown(source, "no headlines")
    prompt = (f"Idea: supplier {sup} <- principal customer {cust}.\n"
              f"Recent {cust} (customer) headlines:\n{_headlines_block(cust_items)}\n"
              f"Recent {sup} (supplier) headlines:\n{_headlines_block(sup_items)}\n" + _SCHEMA)
    try:
        text = complete(prompt, model=OPUS, system=_SRC_SYS)
    except AnthropicError:
        return _unknown(source, "llm unavailable")
    return _verdict_from(source, parse_json(text))


def rss_agent(idea: dict) -> dict:
    cust, sup = idea["customer"], idea["supplier"]
    return _source_verdict("rss", cust, sup, google_rss(cust), google_rss(sup))


def tiingo_agent(idea: dict) -> dict:
    cust, sup = idea["customer"], idea["supplier"]
    start = None
    if idea.get("entry"):
        try:
            start = (date.fromisoformat(idea["entry"]) - timedelta(days=21)).isoformat()
        except ValueError:
            start = None
    return _source_verdict("tiingo", cust, sup, tiingo_news(cust, start=start),
                           tiingo_news(sup, start=start))


def web_agent(idea: dict) -> dict:
    cust, sup = idea["customer"], idea["supplier"]
    prompt = (f"Search recent (~30 days) news on customer {cust} and supplier {sup}. "
              f"Idea: supplier {sup} lags its principal customer {cust}.\n" + _SCHEMA)
    try:
        text = complete(prompt, model=OPUS, system=_SRC_SYS, tools=[WEB_SEARCH_TOOL], max_tokens=1500)
    except AnthropicError:
        return _unknown("web", "web search unavailable")
    return _verdict_from("web", parse_json(text))


def _majority(verdicts: list) -> dict:
    """Deterministic reducer (also the reconcile fallback): mode of known catalysts; confounding
    is 'yes' if ANY known source says yes (conservative)."""
    known = [v for v in verdicts if v.get("customer_catalyst") not in (None, "unknown")]
    if not known:
        return {"customer_catalyst": "none", "confounding": "no", "confidence": "low",
                "note": "no usable news from any source"}
    cat = Counter(v["customer_catalyst"] for v in known).most_common(1)[0][0]
    conf = "yes" if any(v.get("confounding_supplier_news") == "yes" for v in known) else "no"
    n, agree = len(known), sum(1 for v in known if v["customer_catalyst"] == cat)
    confidence = "high" if agree == n and n >= 2 else "med" if agree > n / 2 else "low"
    return {"customer_catalyst": cat, "confounding": conf, "confidence": confidence,
            "note": f"{agree}/{n} sources agree ({cat}); confounding={conf}"}
