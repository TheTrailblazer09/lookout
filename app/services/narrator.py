"""The narrator: a local model turns a fact sheet into sentences.

The rule that makes this defensible: **the model never supplies a number.**
It receives a JSON fact sheet built entirely from model output, writes
prose, and then every numeral in that prose is checked against the facts it
was given. A number that isn't in the sheet means the model invented it, so
we retry once and then fall back to a template that cannot hallucinate.

That check is cheap, it is the difference between "an LLM wrote this" and
"an LLM phrased numbers our models computed", and it is the thing to show a
judge who asks how you stop hallucination.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from config import get_config

cfg = get_config()
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
THOUSANDS = re.compile(r"(?<=\d),(?=\d)")   # "$10,123" is one number, not two

SYSTEM = (
    "You write short, plain-English portfolio alerts for an ordinary investor. "
    "Rules: use ONLY numbers that appear in the JSON you are given; never invent "
    "or estimate a figure; never give advice about buying or selling; no jargon. "
    'Reply with JSON only: {"title": "...", "why": "...", "history": "..."} where '
    "title is under 10 words, why is 1-2 sentences about what this means for this "
    "portfolio, and history is 1 sentence about the past pattern."
)


def available() -> bool:
    try:
        with urllib.request.urlopen(f"{cfg.OLLAMA_URL}/api/tags", timeout=3):
            return True
    except Exception:  # noqa: BLE001
        return False


def _ask(model: str, facts: dict, timeout: int) -> dict:
    body = json.dumps({
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0.2},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": json.dumps(facts)}],
    }).encode()
    req = urllib.request.Request(f"{cfg.OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read())
    return json.loads(payload["message"]["content"])


def _fact_numbers(facts) -> list[float]:
    out: list[float] = []

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            out.append(float(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            for m in NUMBER.findall(THOUSANDS.sub("", v)):
                out.append(float(m))
    walk(facts)
    return out


def grounded(text: str, facts: dict) -> tuple[bool, list[float]]:
    """Every numeral in the prose must match a fact, allowing for rounding."""
    allowed = _fact_numbers(facts)
    bad = []
    cleaned = THOUSANDS.sub("", text or "")
    for token in NUMBER.findall(cleaned):
        x = float(token)
        if not any(abs(x - f) <= max(0.06, abs(f) * 0.02) or abs(x - round(f)) < 0.51
                   for f in allowed):
            bad.append(x)
    return (not bad), bad


def template(facts: dict) -> dict:
    """Grounded by construction: every number comes straight from the sheet."""
    t = facts["ticker"]
    why = (f"{t} is {facts['weight_pct']}% of your portfolio "
           f"(about ${facts['position_usd']:,}). Today's move changed your "
           f"portfolio by about {facts['portfolio_impact_pct']}%.")
    if facts.get("n_past"):
        history = (f"Across {facts['n_past']} similar past events, {t} moved about "
                   f"{facts['typical_move_pct']}% over the following days, against "
                   f"{facts['baseline_move_pct']}% in an ordinary stretch.")
    else:
        history = f"Lookout has no comparable past events for {t} yet."
    return {"title": facts["headline"], "why": why, "history": history}


def narrate(facts: dict, model: str | None = None) -> tuple[dict, str]:
    """Returns (text, how) where how is llm | llm-retry | template."""
    model = model or cfg.LLM_FAST
    for attempt in ("llm", "llm-retry"):
        try:
            out = _ask(model, facts, cfg.LLM_TIMEOUT)
        except Exception:  # noqa: BLE001 - Ollama missing, model not pulled, timeout
            break
        text = " ".join(str(out.get(k, "")) for k in ("title", "why", "history"))
        ok, _bad = grounded(text, facts)
        if ok and out.get("title"):
            return {"title": out.get("title", ""), "why": out.get("why", ""),
                    "history": out.get("history", "")}, attempt
    return template(facts), "template"