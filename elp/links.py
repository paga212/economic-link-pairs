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
