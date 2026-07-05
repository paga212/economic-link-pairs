"""Master/Orchestrator digest (Phase 3): rank + narrate the live paper-trade.

Fable-5 (auto-fallback to Opus 4.8) reads the already-computed paper_state.json rows and
returns ONLY ordering + prose as JSON. Every number the reader sees is pulled from the state
at render time — the model never emits a figure (PLAN.md §2: code computes, LLM narrates).
Pure stdlib.
"""
from __future__ import annotations

from datetime import datetime, timezone

from elp.llm import complete_fallback, parse_json

PRIMARY, FALLBACK = "claude-fable-5", "claude-opus-4-8"

# Code owns this caveat and appends it regardless of what the model returns.
CAVEAT = ("Forward out-of-sample paper-trade, net of costs (spread shorts are Grade-C, "
          "optimistic). The evidence prior is weak; judged against a pre-set 12-month kill "
          "rule. Recommendations only, no execution.")

SYSTEM = (
    "You are the Master/Orchestrator of a customer-supplier lead-lag paper-trading system "
    "(Cohen & Frazzini 2008: a supplier's stock lags news about its principal customer). "
    "You ONLY rank and explain; you NEVER compute, estimate, or state any number — all "
    "returns, P&L and stops are computed elsewhere and displayed next to your text. "
    "Respond with a single JSON object and nothing else."
)


def _prompt(state: dict, notes: dict) -> str:
    lines = ["Open paper trades (supplier <- principal customer | kind | days held | link):"]
    for o in state.get("open", []):
        note = notes.get(o["supplier"], "")
        lines.append(f'- {o["supplier"]} <- {o["customer"]} | {o["kind"]} | {o["days"]}d | {note}')
    if not state.get("open"):
        lines.append("- (none open right now)")
    st = state.get("stats", {}) or {}
    lines.append(f'\nClosed out-of-sample trades scored so far: n={st.get("n") or 0}.')
    lines.append(
        '\nReturn JSON exactly of this shape:\n'
        '{"summary": "one short paragraph reading the book as a whole",\n'
        ' "ranked": [{"supplier": "TICK", "rationale": "one sentence on conviction, grounded '
        'in the economic link — no numbers"}],\n'
        ' "watch": ["short note on any trade needing attention (e.g. thesis weakening, long held)"]}\n'
        'Rank ALL open suppliers, most attractive first. Use only the tickers listed above.'
    )
    return "\n".join(lines)


def build_digest(state: dict, notes: dict) -> dict:
    """Call the Master agent and deterministically merge its ordering/prose with the state
    numbers. Raises (via complete_fallback) on API failure so the caller can fail soft."""
    # Fable-5 runs extended thinking by default; those tokens count against max_tokens, so
    # budget generously (thinking ~1-2k + the JSON ~600). Unused ceiling isn't billed.
    text, model = complete_fallback(_prompt(state, notes), primary=PRIMARY, fallback=FALLBACK,
                                    system=SYSTEM, max_tokens=4096)
    data = parse_json(text) or {}

    open_by_sup = {o["supplier"]: o for o in state.get("open", [])}
    ranked, seen = [], set()
    for r in (data.get("ranked") or []):
        sup = r.get("supplier") if isinstance(r, dict) else None
        if sup in open_by_sup and sup not in seen:      # drop hallucinated / duplicate tickers
            seen.add(sup)
            rationale = str(r.get("rationale") or "").strip() or "—"
            ranked.append({**open_by_sup[sup], "rationale": rationale})
    for sup, o in open_by_sup.items():                  # append any the model skipped
        if sup not in seen:
            ranked.append({**o, "rationale": "—"})

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "model_used": model,
        "summary": str(data.get("summary") or "").strip(),
        "watch": [str(w).strip() for w in (data.get("watch") or []) if str(w).strip()],
        "caveat": CAVEAT,
        "ranked_open": ranked,
    }
