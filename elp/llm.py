"""Minimal Anthropic API client for the LLM extraction step (Phase B).

Reads the key from ANTHROPIC_API_KEY or a gitignored key file; sends it as a header, never
prints it. Defaults to Haiku (cheap bulk). Pure stdlib.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

MODEL = "claude-haiku-4-5"
_URL = "https://api.anthropic.com/v1/messages"


def _key() -> str:
    raw = os.environ.get("ANTHROPIC_API_KEY")
    if not raw:
        for p in (".anthropic_key", ".anthropic.key", os.path.expanduser("~/.anthropic_key")):
            if os.path.exists(p):
                raw = open(p).read()
                break
    if not raw:
        raise RuntimeError("No Anthropic key (set ANTHROPIC_API_KEY or create ~/.anthropic_key)")
    k = raw.strip()
    if "=" in k:                      # tolerate a pasted `export KEY='...'` line
        k = k.split("=", 1)[1]
    return k.strip().strip("'").strip('"').strip()


def complete(prompt: str, model: str = MODEL, max_tokens: int = 1024, system: str | None = None) -> str:
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    req = urllib.request.Request(_URL, data=json.dumps(body).encode(), headers={
        "x-api-key": _key(), "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Anthropic HTTP {e.code}") from None  # never surface the key
    return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")


def extract_json(prompt: str, **kw):
    """Call complete() and parse the first JSON array/object in the reply (None on failure)."""
    m = re.search(r"(\[.*\]|\{.*\})", complete(prompt, **kw), re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
