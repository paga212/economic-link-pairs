"""Customer->supplier link universe.

`load_universe()` returns the Phase-B LLM-extracted, disclosure-derived links
(universe_links.json) when present, else falls back to the hand-curated HIGHSIGNAL_LINKS.
The LINKS / CURATED_DIVERSE sets remain for the older phase scripts.
"""
import json
import os

LINKS: list[tuple[str, str, str]] = [
    ("CRUS", "AAPL", "Cirrus Logic — Apple historically the large majority of sales"),
    ("SWKS", "AAPL", "Skyworks Solutions — Apple a large share of sales"),
    ("QRVO", "AAPL", "Qorvo — Apple a major customer"),
    ("JBL", "AAPL", "Jabil — Apple its largest customer historically"),
    ("UCTT", "AMAT", "Ultra Clean Holdings — Applied Materials a principal customer"),
]

# A more customer-DIVERSE curated set so the cross-sectional long/short is
# non-degenerate (suppliers must have different customers to get different signals).
# Illustrative, well-known relationships — NOT verified point-in-time links. For
# engine validation only; any performance number off this set is not a valid alpha
# (survivorship-biased still-listed names, tiny universe). (supplier, customer, note).
CURATED_DIVERSE: list[tuple[str, str, str]] = [
    ("SWKS", "AAPL", "Skyworks — Apple"),
    ("CRUS", "AAPL", "Cirrus Logic — Apple"),
    ("QRVO", "AAPL", "Qorvo — Apple"),
    ("UCTT", "AMAT", "Ultra Clean — Applied Materials"),
    ("AXL", "GM", "American Axle — GM a dominant customer"),
    ("LEA", "GM", "Lear — auto OEMs incl. GM"),
    ("SPR", "BA", "Spirit AeroSystems — Boeing a dominant customer"),
    ("TGI", "BA", "Triumph Group — Boeing a major customer"),
]

# Live paper-trade universe: hand-curated, widely-reported, still-listed high-signal
# supplier->customer links with diverse customers (so the cross-section isn't degenerate)
# and long Tiingo history. HAND-CURATED BEST-GUESSES, not disclosure-derived or
# point-in-time — the Phase B LLM+EDGAR step will replace/augment these with real
# disclosed links once the Anthropic key is available. (supplier, customer, note).
HIGHSIGNAL_LINKS: list[tuple[str, str, str]] = [
    # Apple deliberately capped at a few names so the cross-section isn't Apple-driven;
    # the engine is customer-agnostic and Phase B (LLM links) diversifies this broadly.
    ("SWKS", "AAPL", "Skyworks — Apple"),
    ("CRUS", "AAPL", "Cirrus Logic — Apple"),
    ("GLW", "AAPL", "Corning — Apple (cover glass)"),
    ("SMCI", "NVDA", "Super Micro — Nvidia (GPU servers)"),
    ("UCTT", "AMAT", "Ultra Clean — Applied Materials"),
    ("MKSI", "AMAT", "MKS Instruments — semiconductor equipment"),
    ("ICHR", "LRCX", "Ichor — Lam Research"),
    ("UCTT", "LRCX", "Ultra Clean — Lam Research"),
    ("AXL", "GM", "American Axle — GM"),
    ("LEA", "GM", "Lear — GM"),
    ("DAN", "F", "Dana — Ford"),
    ("ALV", "F", "Autoliv — Ford"),
    ("TGI", "BA", "Triumph Group — Boeing"),
    ("HXL", "BA", "Hexcel — Boeing (composites)"),
    ("BALL", "KO", "Ball — Coca-Cola (cans)"),
    ("BALL", "PEP", "Ball — PepsiCo (cans)"),
]


def load_universe(path: str = "universe_links.json", min_conf: float = 0.6):
    """Phase-B disclosure-derived links (named + confident), else the hand-curated set.

    Returns list of (supplier, customer, note). The daily tracker uses this; refresh the
    file with phase_b_build.py (it is NOT re-extracted on every run).
    """
    if os.path.exists(path):
        try:
            data = json.load(open(path))
            seen, out = set(), []
            for x in data:
                s, c = x.get("supplier"), x.get("customer")
                if not (s and c) or s == c or not x.get("named"):
                    continue
                if (x.get("confidence") or 0) < min_conf or (s, c) in seen:
                    continue
                seen.add((s, c))
                out.append((s, c, str(x.get("customer_raw", ""))))
            if out:
                return out
        except Exception:
            pass
    return HIGHSIGNAL_LINKS
