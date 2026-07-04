# EDGAR extraction reality check (Phase 2a finding, 2026-07-04)

Built the deterministic EDGAR extractor (`elp/edgar.py`) and ran it against known-answer
suppliers. **The plumbing works** (full-text search, submissions API, filing fetch,
CIK↔ticker resolution, regex parse all execute; offline parser tests pass). **But live
recall of named customer + concentration % is poor**, and the diagnosis matters for the
whole project.

## What we saw

On 5 known Apple/AMAT suppliers' latest 10-Ks:
- **CRUS, SWKS, JBL, UCTT** → *no* customer disclosure extracted (despite all having a
  well-known major customer).
- **QRVO** → extracted Samsung (10%) correctly + one false positive ("U.S" 37%). Samsung
  is unresolved because it isn't US-listed.
- **AXL / SPR** → not in the current SEC ticker map (SPR delisted into the Boeing
  acquisition; AXL a map gap).

## Why (the real reason, from SWKS's 2025 10-K)

The concentration is disclosed but **decoupled from the customer name**:
- *"...one customer accounted for greater than ten percent of our net revenue."* — no name, and **">10%" not a number**.
- *"...three customers represented 82% of our aggregate..."* — aggregated, unnamed.
- "Apple Inc." appears only inside a ~20-name **"key customers" list** ("Amazon, Apple, Arcadyan, Arris, Bose, Ciena, Cisco, Ericsson, ...") with no link to the concentration figure.

So the information often **is not in any single parseable sentence**, and sometimes the
name and/or the exact % are simply **not disclosed**. This corroborates Ellis, Fee &
Thomas (2012, JAR) that firms frequently withhold customer identity. It also explains why
Cohen-Frazzini used **Compustat segment data** (1980-2004), where the customer name is
structured and naming was more common — the free-EDGAR path is materially harder than "use
an LLM to parse the sentence," because for many filers there is no sentence to parse.

Recall is **variable by filer**: some name a customer next to the % (QRVO→Samsung
extracted fine); many don't (SWKS). The named+quantified subset is extractable at decent
precision; the unnamed subset is not, by regex *or* naive LLM-sentence-parsing.

## Implications for link sourcing

1. A comprehensive **current** customer-supplier link set from free EDGAR is not cheaply
   achievable — a large fraction of concentration disclosures are unnamed/unquantified.
2. The **named** subset is extractable and usable (higher precision, lower coverage).
3. The **historical** C-F free dataset (names + %, 1980-2004) remains the best free link
   source for a *backtest*, but it's stale and permno-keyed (needs permno→ticker).

## Options (decision needed)

| Option | Coverage | Effort/cost | Risk |
|---|---|---|---|
| A. Named-only current links from EDGAR (extract where named+quantified, skip the rest) | Low (a minority of filers) | Low (LLM parse of named disclosures) | Thin universe — few live ideas/month |
| B. + LLM *inference* of unnamed customers from the key-customer list + external knowledge, with a confidence flag | Higher | LLM (needs Anthropic key) | Inference ≠ disclosure; false links pollute a fragile signal |
| C. Historical-only: build the backtest on the free C-F dataset (solve permno→ticker), no live current-link engine | Backtest only | Medium (crosswalk + delisted prices) | No live recommender from free data |
| D. Pay for structured supply-chain data (FactSet Revere / Bloomberg SPLC) | Full | 5-figure institutional (off budget) | Cost |

**Recommendation:** A + a cautious, clearly-flagged slice of B — extract named+quantified
links at high precision, use the LLM to (i) robustly parse the named disclosures and (ii)
optionally propose an unnamed customer's identity *with a confidence score we can threshold
or exclude*. Measure precision/recall against the C-F overlap before trusting any of it.
This keeps the live universe honest (real disclosed links) and treats inference as an
opt-in, auditable add-on — not the backbone.

**Open question for the user:** how much inference risk (Option B) is acceptable in the
live link set, given the signal is already fragile and a wrong link injects pure noise?
