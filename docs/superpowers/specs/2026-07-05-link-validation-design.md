# Link validation — clean up bad customer-supplier links + a durable guard

**Status:** design approved 2026-07-05 (brainstormed with Pierre). Awaiting spec review → implementation plan.
**Builds on:** the `expression-engine` branch (uses `elp/liquidity.py::is_tradeable`/`dollar_adv` and `elp/tiingo.py::fetch_daily_bars`, both added there). Assume that branch is merged (or this branch rebases onto it) first.
**Reuses:** `elp/edgar.py::norm` (name normalization), stdlib `difflib`, `urllib`.

## 1. Context and goal

Phase B (LLM extraction from EDGAR) populates `universe_links.json` — 26 links, all `named`, all high-confidence (0.8–1.0). Two are wrong, and **confidence does not catch them because it measures the LLM's *extraction* certainty, not its name→ticker *resolution* correctness**:

- `NRP → ATGL` (`customer_raw: "Alpha"`, conf 0.95) — the customer NAME is read correctly but resolved to the WRONG ticker (the coal customer is Alpha Metallurgical = `AMR`, not `ATGL`). A wrong-but-liquid ticker: not caught by liquidity or confidence, and it poisons the *signal*.
- `MZTI → WMT` (`customer_raw: "Walmart Inc."`, conf 0.99) — `MZTI` is a real, liquid company ($115, $44M ADV) but its price series has a **corrupt $0.07 bar**; the customer (Walmart) is fine.

Two distinct failure modes: **wrong ticker resolution** (bad signal) and **bad price data / glitch bar** (bad P&L). The liquidity gate shipped with the expression engine catches penny/illiquid junk incidentally but not a wrong-but-liquid ticker.

**Goal:** clean up the current 26 links now, AND add a durable lightweight guard that validates links on every Phase-B rebuild — catching BOTH failure modes.

## 2. The checks (`validate_links`)

A function `validate_links(links, bars_fn=fetch_daily_bars, sec_map=load_sec_map) -> (good, rejected)` runs each `(supplier, customer, customer_raw)` link through three cheap checks and quarantines failures with a reason. Dependencies are injectable so unit tests run offline.

1. **Supplier price-sanity** (catches MZTI-class): fetch supplier bars; reject if the series is missing, fails `is_tradeable` (price ≥ $5, ADV ≥ $5M — existing), or has an absurd adjacent-bar jump (any day-over-day ratio > `GAP_MAX` ≈ 5×, which flags the $0.07↔$115 glitch). Reason: `illiquid` or `bad_bars`. The supplier is the leg we trade, so its data must be clean.
2. **Customer price-sanity**: same liquidity + gap check on the customer ticker (the signal source must be a real, liquid name). Reason: `illiquid` / `bad_bars`.
3. **Customer name↔ticker** (catches NRP→ATGL): cross-check the stored customer ticker against `customer_raw` via the SEC reference (§3). Reason: `name_mismatch` or `ambiguous`.

A link is **kept only if it passes all three checks**; the first failing check's reason is recorded and the link is quarantined. We do NOT repair bad bars or re-resolve wrong tickers automatically — failing links are simply quarantined (YAGNI). The supplier ticker is not name-checked (it comes from the filing's own EDGAR metadata, which is reliable; only the extracted *customer* name→ticker hop is error-prone).

## 3. Name↔ticker mechanics

- **Reference:** SEC `company_tickers.json` (`ticker → {cik, title}`), fetched once with a descriptive `User-Agent` (SEC requirement) and cached to a gitignored local file (`sec_tickers.json`); refetched if missing. `load_sec_map()` returns `{ticker: title}` plus the title list for reverse lookup.
- **Forward check:** `similar(norm(customer_raw), norm(sec_map[stored_ticker]))` via `difflib.SequenceMatcher`; reject `name_mismatch` if below `NAME_SIM_MIN` ≈ 0.6.
- **Ambiguity guard:** re-resolve `customer_raw` against all SEC titles (`difflib.get_close_matches`); if it does not map to a single confident ticker (e.g. bare "Alpha" matches many), reject `ambiguous`. This is why `NRP→ATGL` dies: "Alpha" is not confidently resolvable and `ATGL`'s real title won't match it.
- Net on current data: `ADSK→SNX` ("TD Synnex Corporation" ≈ SNX title) passes; `NRP→ATGL` fails name/ambiguity; `MZTI→WMT` fails the supplier gap-check.

## 4. Handling + where it runs

- **Quarantine, never silent-drop.** `rejected` = `[{supplier, customer, customer_raw, reason}]`. Good links → `universe_links.json`; rejected → **`rejected_links.json`** (audit trail); print `kept N, rejected M: <reasons>`.
- **New module `elp/linkcheck.py`** holds `validate_links`, `load_sec_map`, and the checks. Reuses `is_tradeable`/`dollar_adv`, `fetch_daily_bars`, `edgar.norm`, `difflib`. No new deps.
- **Standalone entry `linkcheck.py`** (mirrors `track.py`): load current `universe_links.json` → `validate_links` → write cleaned file + `rejected_links.json` → print summary. Runs the one-time cleanup and any re-check.
- **Durable guard:** `phase_b_build.py` calls `validate_links` after extraction, before writing `universe_links.json`, so every rebuild is auto-validated; rejects go to `rejected_links.json`.
- **`load_universe` is unchanged** — reads the already-validated `universe_links.json`; `track.py` pays no per-run validation cost.

## 5. One-time cleanup (run now)

`python3 linkcheck.py` on the current 26 → cleaned `universe_links.json` + `rejected_links.json`. Expect `NRP→ATGL` (ambiguous/name-mismatch) and `MZTI→WMT` (supplier `bad_bars`) rejected; review `rejected_links.json` for false positives among the other 24 and tune `NAME_SIM_MIN`/`GAP_MAX` or add a small whitelist if needed; commit both files. The live book picks up the cleaner universe on the next `track.py`.

## 6. Config (frozen, documented)

`GAP_MAX ≈ 5.0` (max adjacent-bar ratio), `NAME_SIM_MIN ≈ 0.6` (difflib ratio floor), plus the liquidity floors reused from `elp/liquidity.py`. `SEC_USER_AGENT` = a descriptive string with a contact (SEC requires it). All module constants; do not tune on live outcomes.

## 7. Testing (offline)

`validate_links` with a stub `bars_fn` and stub `sec_map` (no network):
- good link (name matches, clean liquid bars) → **kept**;
- customer ticker whose SEC title ≠ `customer_raw` → `name_mismatch`;
- generic/ambiguous `customer_raw` → `ambiguous`;
- supplier series with a > `GAP_MAX` adjacent jump → `bad_bars`;
- penny/illiquid ticker → `illiquid`;
- and a direct test of the `norm`+`difflib` similarity helper.
All deterministic and offline. A separate, network-touching smoke (`python3 linkcheck.py`) is run by hand during the one-time cleanup, not in the unit suite.

## 8. Out of scope
- Repairing bad price bars or auto-correcting wrong tickers (we reject, not fix).
- Supplier name↔ticker validation (supplier ticker is reliable from filing metadata).
- Re-running the full Phase-B LLM extraction (the guard validates whatever extraction produced).
- The options-overlay and expression-engine work (separate branches/plans).
