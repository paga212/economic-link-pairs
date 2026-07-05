# Link validation — clean up bad customer-supplier links + a durable guard

**Status:** design approved 2026-07-05 (brainstormed with Pierre). Awaiting spec review → implementation plan.
**Builds on:** the `expression-engine` branch (uses `elp/liquidity.py::is_tradeable`/`dollar_adv` and `elp/tiingo.py::fetch_daily_bars`, both added there). Assume that branch is merged (or this branch rebases onto it) first.
**Reuses:** `elp/edgar.py` — `norm` (name normalization), **`load_ticker_map()` (already loads SEC `company_tickers.json` with the required User-Agent)**, and `resolve`. Plus stdlib `difflib`. No new SEC loader is needed.

## 1. Context and goal

Phase B (LLM extraction from EDGAR) populates `universe_links.json` — 26 links, all `named`, all high-confidence (0.8–1.0). Two are wrong, and **confidence does not catch them because it measures the LLM's *extraction* certainty, not its name→ticker *resolution* correctness**:

- `NRP → ATGL` (`customer_raw: "Alpha"`, conf 0.95) — the customer NAME is read correctly but resolved to the WRONG ticker (the coal customer is Alpha Metallurgical = `AMR`, not `ATGL`). A wrong-but-liquid ticker: not caught by liquidity or confidence, and it poisons the *signal*.
- `MZTI → WMT` (`customer_raw: "Walmart Inc."`, conf 0.99) — `MZTI` is a real, liquid company ($115, $44M ADV) but its price series has a **corrupt $0.07 bar**; the customer (Walmart) is fine.

Two distinct failure modes: **wrong ticker resolution** (bad signal) and **bad price data / glitch bar** (bad P&L). The liquidity gate shipped with the expression engine catches penny/illiquid junk incidentally but not a wrong-but-liquid ticker.

**Goal:** clean up the current 26 links now, AND add a durable lightweight guard that validates links on every Phase-B rebuild — catching BOTH failure modes.

## 2. The checks (`validate_links`)

A function `validate_links(links, bars_fn=fetch_daily_bars, ticker_map=None) -> (good, rejected)` runs each link dict (`{supplier, customer, customer_raw, …}`, the `universe_links.json` shape) through three cheap checks and quarantines failures with a reason. `ticker_map` is `(by_cik, by_name)` from `edgar.load_ticker_map()` (loaded once by the caller; `None` → load it). Both `bars_fn` and `ticker_map` are injectable so unit tests pass stubs and run offline.

1. **Supplier price-sanity** (catches MZTI-class): fetch supplier bars; reject if the series is missing, fails `is_tradeable` (price ≥ $5, ADV ≥ $5M — existing), or has an absurd adjacent-bar jump (any day-over-day ratio > `GAP_MAX` ≈ 5×, which flags the $0.07↔$115 glitch). Reason: `illiquid` or `bad_bars`. The supplier is the leg we trade, so its data must be clean.
2. **Customer price-sanity**: same liquidity + gap check on the customer ticker (the signal source must be a real, liquid name). Reason: `illiquid` / `bad_bars`.
3. **Customer name↔ticker** (catches NRP→ATGL): cross-check the stored customer ticker against `customer_raw` via the SEC reference (§3). Reason: `name_mismatch` or `ambiguous`.

A link is **kept only if it passes all three checks**; the first failing check's reason is recorded and the link is quarantined. We do NOT repair bad bars or re-resolve wrong tickers automatically — failing links are simply quarantined (YAGNI). The supplier ticker is not name-checked (it comes from the filing's own EDGAR metadata, which is reliable; only the extracted *customer* name→ticker hop is error-prone).

## 3. Name↔ticker mechanics (reuse the existing SEC infra)

The SEC reference already exists: `edgar.load_ticker_map()` returns `(by_cik, by_name)` from `company_tickers.json`, and `edgar.norm` normalizes names (drops Inc./Corp./Group/Technology/… suffixes, punctuation, case). **Reuse these — do not build a second SEC loader.** Derive `ticker_to_title = {v["ticker"]: v["title"] for v in by_cik.values()}`.

The customer name↔ticker check has three parts; the link is rejected on the **first** that fails:

1. **Existence** — the stored customer ticker must be a real SEC ticker (present in `ticker_to_title`); else `unknown_ticker`.
2. **Ambiguity (the load-bearing check that catches NRP→ATGL)** — `customer_raw` must be specific enough to identify one company. Reject `ambiguous` if the count of SEC titles whose normalized token-set contains **all** tokens of `norm(customer_raw)` exceeds `AMBIG_MAX` (≈ 3). A truncated "Alpha" is a leading token of many companies (Alphabet, Alpha Pro Tech, Alpha Metallurgical, …) → ambiguous; "Walmart"/"TD Synnex" each match one → fine. **Why this and not similarity:** the LLM truncated "Alpha Metallurgical Resources" to "Alpha", and `resolve("Alpha")` landed on `ATGL` (a different "Alpha …" company). "Alpha" and `ATGL`'s suffix-stripped title *both* normalize to "alpha", so a forward similarity check would score ~1.0 and pass — only the ambiguity count catches it.
3. **Consistency** — `difflib.SequenceMatcher` ratio of `norm(customer_raw)` vs `norm(ticker_to_title[ticker])` must be ≥ `NAME_SIM_MIN` (≈ 0.6); else `name_mismatch`. Catches a resolved ticker whose real company name is unrelated to the extracted name (the case where the wrong ticker's title does NOT coincidentally normalize to the raw name).

Net on current data: `ADSK→SNX` ("TD Synnex Corporation" ≈ SNX title, unambiguous) passes; `NRP→ATGL` fails **ambiguity**; `MZTI→WMT` fails the **supplier gap-check** (customer WMT/"Walmart" is correct).

## 4. Handling + where it runs

- **Quarantine, never silent-drop.** `rejected` = `[{supplier, customer, customer_raw, reason}]`. Good links → `universe_links.json`; rejected → **`rejected_links.json`** (audit trail); print `kept N, rejected M: <reasons>`.
- **New module `elp/linkcheck.py`** holds `validate_links` and the three checks. Reuses `is_tradeable`/`dollar_adv` (liquidity), `fetch_daily_bars` (bars), `edgar.load_ticker_map`/`edgar.norm` (SEC map + normalization), and stdlib `difflib`. No new SEC loader, no new deps.
- **Standalone entry `linkcheck.py`** (mirrors `track.py`): load current `universe_links.json` → `validate_links` → write cleaned file + `rejected_links.json` → print summary. Runs the one-time cleanup and any re-check.
- **Durable guard:** `phase_b_build.py` calls `validate_links` after extraction, before writing `universe_links.json`, so every rebuild is auto-validated; rejects go to `rejected_links.json`.
- **`load_universe` is unchanged** — reads the already-validated `universe_links.json`; `track.py` pays no per-run validation cost.

## 5. One-time cleanup (run now)

`python3 linkcheck.py` on the current 26 → cleaned `universe_links.json` + `rejected_links.json`. Expect `NRP→ATGL` (ambiguous/name-mismatch) and `MZTI→WMT` (supplier `bad_bars`) rejected; review `rejected_links.json` for false positives among the other 24 and tune `NAME_SIM_MIN`/`GAP_MAX` or add a small whitelist if needed; commit both files. The live book picks up the cleaner universe on the next `track.py`.

## 6. Config (frozen, documented)

`GAP_MAX ≈ 5.0` (max adjacent-bar ratio), `NAME_SIM_MIN ≈ 0.6` (difflib ratio floor), `AMBIG_MAX ≈ 3` (max SEC titles a `customer_raw` may match before it's "ambiguous"), plus the liquidity floors reused from `elp/liquidity.py`. The SEC User-Agent is already set in `edgar.py` (`UA`). All module constants; do not tune on live outcomes.

## 7. Testing (offline)

`validate_links` with a stub `bars_fn` and stub `ticker_map` (no network):
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
