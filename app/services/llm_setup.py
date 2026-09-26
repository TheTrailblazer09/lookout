"""Getting the local model ready, without anyone touching a terminal.

Two jobs the frontend can drive:

  status()  is Ollama running, and is our model downloaded?
  pull()    download the model, reporting progress as it goes.

Downloading is a plain HTTP call to Ollama, so no shell is involved.
Starting the server is different: `ollama serve` is a long-lived process,
so we spawn it detached and wait for it to answer. If the binary isn't
installed we say so plainly rather than failing in a confusing way, since
that is the one step a person genuinely has to do once.

Progress lives in memory, so the frontend polls status() while a pull runs.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

from config import get_config

cfg = get_config()

_state = {
    "pulling": False,
    "model": None,
    "percent": 0.0,
    "stage": "",
    "error": None,
    "finished_at": None,
}
_lock = threading.Lock()


# --- talking to Ollama ----------------------------------------------------

def _get(path: str, timeout: int = 3):
    with urllib.request.urlopen(f"{cfg.OLLAMA_URL}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def server_running() -> bool:
    try:
        _get("/api/tags")
        return True
    except Exception:  # noqa: BLE001
        return False


def installed_models() -> list[str]:
    try:
        return [m["name"] for m in _get("/api/tags").get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def _has(model: str, installed: list[str]) -> bool:
    """Ollama reports 'qwen3.5:9b'; a bare name means the :latest tag."""
    want = model if ":" in model else f"{model}:latest"
    return any(m == want or m.split(":")[0] == want.split(":")[0] for m in installed)


def binary_present() -> bool:
    return shutil.which("ollama") is not None


# --- starting the server --------------------------------------------------

def start_server(wait_seconds: int = 20) -> dict:
    if server_running():
        return {"started": False, "running": True, "message": "Already running."}
    if not binary_present():
        return {"started": False, "running": False,
                "message": "Ollama is not installed. Install it once from "
                           "https://ollama.com/download, then this works by itself."}
    try:
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)  # survives this request
    except Exception as exc:  # noqa: BLE001
        return {"started": False, "running": False, "message": f"Could not start: {exc}"}

    for _ in range(wait_seconds * 2):
        if server_running():
            return {"started": True, "running": True, "message": "Ollama started."}
        time.sleep(0.5)
    return {"started": True, "running": False,
            "message": "Started Ollama but it has not answered yet; try again shortly."}


# --- pulling a model ------------------------------------------------------

def _pull_worker(model: str) -> None:
    body = json.dumps({"model": model, "stream": True}).encode()
    req = urllib.request.Request(f"{cfg.OLLAMA_URL}/api/pull", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=None) as resp:
            for raw in resp:
                if not raw.strip():
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if msg.get("error"):
                    with _lock:
                        _state.update(error=msg["error"], pulling=False)
                    return
                total, done = msg.get("total"), msg.get("completed")
                with _lock:
                    _state["stage"] = msg.get("status", "")
                    if total:
                        _state["percent"] = round(100.0 * (done or 0) / total, 1)
        with _lock:
            _state.update(pulling=False, percent=100.0, stage="ready",
                          finished_at=time.time())
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _state.update(error=str(exc), pulling=False)


def pull(model: str | None = None) -> dict:
    """Start a download in the background. Safe to call twice."""
    model = model or cfg.LLM_FAST
    with _lock:
        if _state["pulling"]:
            return {"started": False, "message": f"Already downloading {_state['model']}."}
        if not server_running():
            return {"started": False, "message": "Ollama is not running. Start it first."}
        if _has(model, installed_models()):
            return {"started": False, "message": f"{model} is already installed."}
        _state.update(pulling=True, model=model, percent=0.0, stage="starting",
                      error=None, finished_at=None)
    threading.Thread(target=_pull_worker, args=(model,), daemon=True).start()
    return {"started": True, "model": model,
            "message": f"Downloading {model}. Poll /llm/status for progress."}


# --- what the frontend reads ---------------------------------------------

def status() -> dict:
    running = server_running()
    installed = installed_models() if running else []
    model = cfg.LLM_FAST
    ready = running and _has(model, installed)
    with _lock:
        progress = dict(_state)

    if ready:
        message = f"{model} is ready. Alerts will be written by the local model."
    elif progress["pulling"]:
        message = f"Downloading {progress['model']} ({progress['percent']}%)."
    elif progress["error"]:
        message = f"Download failed: {progress['error']}"
    elif running:
        message = f"Ollama is running but {model} is not downloaded yet."
    elif binary_present():
        message = "Ollama is installed but not running."
    else:
        message = ("Ollama is not installed. Alerts still work; they are written "
                   "from templates instead of by the model.")

    return {
        "ready": ready,
        "server_running": running,
        "binary_present": binary_present(),
        "model": model,
        "installed_models": installed,
        "downloading": progress["pulling"],
        "percent": progress["percent"],
        "stage": progress["stage"],
        "error": progress["error"],
        "message": message,
        # alerts never block on this: templates are the fallback
        "fallback": "templates",
    }


def ensure(model: str | None = None) -> dict:
    """One call the frontend can make on first load: start the server if it
    can, begin the download if needed, and report where things stand."""
    model = model or cfg.LLM_FAST
    steps = []
    if not server_running():
        steps.append(start_server())
    if server_running() and not _has(model, installed_models()):
        steps.append(pull(model))
    return {"steps": steps, "status": status()}