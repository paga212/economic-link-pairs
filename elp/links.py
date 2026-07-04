"""Hardcoded customer->supplier links for Phase 0 validation.

Illustrative, widely-reported high-concentration supplier/customer relationships,
both legs still listed so Yahoo has data. These are NOT a verified point-in-time
link set and the concentration notes are approximate from memory — the real links
come from the free Cohen-Frazzini dataset (Phase 1) and DIY EDGAR extraction
(Phase 2). Each entry: (supplier, customer, note).
"""

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
