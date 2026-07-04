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
