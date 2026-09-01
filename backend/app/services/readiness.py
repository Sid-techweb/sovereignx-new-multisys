"""
Tracks model READINESS separately from FastAPI process LIVENESS.

Liveness (the process is up, /health responds) must not depend on model
initialization -- BGE-M3's cold load alone measured ~18.5s, which is 18.5s
of the whole backend refusing every request (including /health) under the
old synchronous-startup-event design. Readiness (are the LLM/embedding
model actually warm enough to serve AI requests) is a separate, slower-
arriving signal, set by background warmup threads kicked off at startup
(see main.py's startup_event) rather than blocking ASGI startup itself.

Deliberately minimal: two booleans + timestamps, no state machine, no
per-request coupling beyond what chat/service.py's bounded wait (Phase 16)
needs. Not a general-purpose registry -- if a third model is added later,
extend this in the same spirit, don't build a framework preemptively.
"""
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class ReadinessState:
    llm_ready: bool = False
    llm_error: Optional[str] = None
    embedding_ready: bool = False
    embedding_error: Optional[str] = None
    warmup_started_at: Optional[float] = None
    llm_ready_at: Optional[float] = None
    embedding_ready_at: Optional[float] = None


_lock = threading.Lock()
_state = ReadinessState()


def reset_for_testing() -> None:
    global _state
    with _lock:
        _state = ReadinessState()


def mark_warmup_started() -> None:
    with _lock:
        _state.warmup_started_at = time.time()


def mark_llm_ready(error: Optional[str] = None) -> None:
    with _lock:
        _state.llm_ready = error is None
        _state.llm_error = error
        _state.llm_ready_at = time.time()


def mark_embedding_ready(error: Optional[str] = None) -> None:
    with _lock:
        _state.embedding_ready = error is None
        _state.embedding_error = error
        _state.embedding_ready_at = time.time()


def get_state() -> ReadinessState:
    with _lock:
        # Return a shallow copy so callers can't mutate shared state.
        return ReadinessState(**_state.__dict__)


def wait_until_ready(which: str, timeout: float) -> bool:
    """
    Bounded poll used by chat/service.py when a request arrives before
    warmup finished (Phase 16) -- `which` is "llm" or "embedding". Returns
    True if ready within `timeout`, False otherwise (caller decides how to
    respond -- see chat/service.py).
    """
    deadline = time.time() + timeout
    attr = "llm_ready" if which == "llm" else "embedding_ready"
    while time.time() < deadline:
        if getattr(get_state(), attr):
            return True
        time.sleep(0.2)
    return getattr(get_state(), attr)
