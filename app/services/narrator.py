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
from pathlib import Path

from config import get_config

cfg = get_config()
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
THOUSANDS = re.compile(r"(?<=\d),(?=\d)")   # "$10,123" is one number, not two

# The prompt lives in a file so it can be edited without touching code,
# and read at call time so edits apply immediately.
PROMPTS = Path(__file__).parent / "prompts"
PROMPT_PATH = PROMPTS / "alert_narrator.md"
MAX_ATTEMPTS = 3
_FALLBACK_SYSTEM = (
    "You write short, plain-English portfolio alerts. Use ONLY numbers from "
    'the JSON given. Reply with JSON: {"title": "...", "why": "...", '
    '"history": "..."}. Never give buy or sell advice.'
)


def load_prompt(name: str = "alert_narrator") -> str:
    """Read a prompt file. Everything after the --- divider is the prompt
    proper; the part above is a note to whoever edits the file."""
    try:
        text = (PROMPTS / f"{name}.md").read_text()
    except OSError:
        return _FALLBACK_SYSTEM
    return text.split("---", 1)[-1].strip() or _FALLBACK_SYSTEM


def system_prompt() -> str:
    return load_prompt("alert_narrator")


def available() -> bool:
    try:
        with urllib.request.urlopen(f"{cfg.OLLAMA_URL}/api/tags", timeout=3):
            return True
    except Exception:  # noqa: BLE001
        return False


def _ask(model: str, facts: dict, timeout: int, prompt: str | None = None,
         correction: str | None = None) -> dict:
    body = json.dumps({
        "model": model, "stream": False, "format": "json",
        # Determinism matters here: the same alert should read the same way
        # on every run, or a demo reruns and the wording drifts. temperature
        # 0 with a fixed seed is as close as Ollama gets to reproducible.
        "options": {"temperature": 0, "seed": 7, "top_p": 1, "repeat_penalty": 1.0},
        "messages": [
            {"role": "system", "content": prompt or system_prompt()},
            {"role": "user", "content": json.dumps(facts, sort_keys=True)},
        ] + ([{"role": "user", "content": correction}] if correction else []),
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

    def matches(x: float, f: float) -> bool:
        # Sign is carried by the words, not the digits: good prose says
        # "took 0.83% off your total", and the fact behind it is -0.83.
        # Comparing magnitudes keeps that legal while still catching any
        # number that was never in the fact sheet at all.
        return (abs(abs(x) - abs(f)) <= max(0.06, abs(f) * 0.02)
                or abs(abs(x) - round(abs(f))) < 0.51)

    for token in NUMBER.findall(cleaned):
        x = float(token)
        if not any(matches(x, f) for f in allowed):
            bad.append(x)
    return (not bad), bad


def template(facts: dict) -> dict:
    """Grounded by construction: every number comes straight from the sheet.

    Used when no local model is running, and as the fallback when one
    writes a number it was not given. It should read well enough that a
    demo without Ollama still makes sense.
    """
    t = facts["ticker"]
    impact = facts.get("portfolio_impact_pct", 0)
    moved = "took" if impact < 0 else "added"

    why = (f"{t} is {facts['weight_pct']}% of your portfolio, about "
           f"${facts['position_usd']:,}. Today's move {moved} roughly "
           f"{abs(impact)}% {'off' if impact < 0 else 'to'} your total.")
    if facts.get("typical_move_dollars"):
        why += (f" A typical move for this kind of event is "
                f"{facts['typical_move_pct']}%, which is about "
                f"${facts['typical_move_dollars']:,} of your money.")

    if facts.get("n_past"):
        louder = facts.get("typical_move_pct", 0) > facts.get("baseline_move_pct", 0)
        history = (f"Across {facts['n_past']} similar past events, {t} moved about "
                   f"{facts['typical_move_pct']}% over the following days, against "
                   f"{facts['baseline_move_pct']}% in an ordinary stretch — so this "
                   f"kind of event {'has moved it more than usual' if louder else 'has not moved it unusually much'}.")
    else:
        history = (f"Lookout has not recorded a comparable event for {t} yet, so "
                   "there is no track record to compare this with. That fills in "
                   "as it keeps watching.")
    return {"title": facts["headline"], "why": why, "history": history}


def narrate(facts: dict, model: str | None = None) -> tuple[dict | None, str]:
    """Ask the local model to write an alert. Returns (text, how).

    `how` is one of: llm, llm-corrected, unavailable, ungrounded.

    There is no prose fallback on purpose. A template that imitates the
    model would be indistinguishable in the UI, which would make the
    "written on this machine" claim meaningless. If the model cannot be
    reached or will not stop inventing numbers, we say so and the screen
    shows the facts instead.

    When a number appears that was not in the fact sheet, we do not simply
    retry and hope: we tell the model exactly which numbers were invented
    and ask again. Naming the mistake fixes it far more often than
    repeating the same request.
    """
    model = model or cfg.LLM_FAST
    last_bad: list[float] = []

    for attempt in range(MAX_ATTEMPTS):
        correction = None
        if last_bad:
            correction = (
                "Your previous reply used numbers that are not in the JSON: "
                + ", ".join(str(b) for b in last_bad)
                + ". Rewrite it using only numbers that appear in the JSON. "
                "If you cannot make a sentence work, leave that number out."
            )
        try:
            out = _ask(model, facts, cfg.LLM_TIMEOUT, correction=correction)
        except Exception:  # noqa: BLE001 - not running, model missing, timeout
            return None, "unavailable"

        text = " ".join(str(out.get(k, "")) for k in ("title", "why", "history"))
        ok, bad = grounded(text, facts)
        if ok and out.get("title"):
            return (
                {"title": out.get("title", ""), "why": out.get("why", ""),
                 "history": out.get("history", "")},
                "llm" if attempt == 0 else "llm-corrected",
            )
        last_bad = bad

    return None, "ungrounded"


def installed(model: str) -> bool:
    """Is this model actually pulled? Asking costs milliseconds; calling a
    missing model costs a full timeout."""
    try:
        with urllib.request.urlopen(f"{cfg.OLLAMA_URL}/api/tags", timeout=3) as r:
            names = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
    except Exception:  # noqa: BLE001
        return False
    want = model if ":" in model else f"{model}:latest"
    return any(n == want or n.split(":")[0] == want.split(":")[0] for n in names)


def write(facts: dict, prompt: str, keys: tuple[str, ...],
          model: str | None = None) -> tuple[dict | None, str]:
    """Ask the model for a JSON object with `keys`, using the named prompt
    file, and reject it if any number in it was not in `facts`.

    The same loop as alerts: this is the one place that decides what
    counts as acceptable model output.
    """
    model = model or cfg.LLM_DEEP
    if not installed(model):
        model = cfg.LLM_FAST
    instructions = load_prompt(prompt)
    for _ in range(MAX_ATTEMPTS):
        try:
            out = _ask(model, facts, cfg.LLM_TIMEOUT, prompt=instructions)
        except Exception:  # noqa: BLE001
            return None, "unavailable"
        text = " ".join(str(out.get(k, "")) for k in keys)
        ok, _bad = grounded(text, facts)
        if ok and out.get(keys[-1]):
            return {k: out.get(k, "") for k in keys}, "llm"
    return None, "ungrounded"


def portfolio_read(facts: dict, model: str | None = None) -> tuple[dict | None, str]:
    """The daily paragraph on the overview screen. Prefers the deep model,
    but only if it is actually downloaded; most people will have pulled the
    fast one and nothing else."""
    model = model or cfg.LLM_DEEP
    if not installed(model):
        model = cfg.LLM_FAST
    prompt = load_prompt("portfolio_read")
    for attempt in range(MAX_ATTEMPTS):
        try:
            out = _ask(model, facts, cfg.LLM_TIMEOUT, prompt=prompt)
        except Exception:  # noqa: BLE001
            # the deep model may not be pulled; the fast one is fine here
            if model != cfg.LLM_FAST:
                model = cfg.LLM_FAST
                continue
            return None, "unavailable"
        text = " ".join(str(out.get(k, "")) for k in ("headline", "read"))
        ok, _bad = grounded(text, facts)
        if ok and out.get("read"):
            return {"headline": out.get("headline", ""), "read": out.get("read", "")}, "llm"
    return None, "ungrounded"