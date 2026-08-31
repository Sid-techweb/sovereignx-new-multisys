"""
Coordinates BGE-M3 embedding-worker residency against Ollama/Qwen residency
so they do not both compete for Windows commit headroom at once.

Why this exists (measured, not assumed): a controlled A/B investigation
proved qwen2.5:7b's *load* fails with a CUDA allocation error specifically
when the BGE-M3 worker is resident (commit headroom ~2.15GB -> load FAILS)
and succeeds the moment the worker is stopped (headroom ~5.93GB -> load
SUCCEEDS), with VRAM essentially unchanged across both conditions. This is
host commit-charge pressure from the worker's ~1.9GB resident footprint,
not a GPU/VRAM problem and not a BGE-M3 stability problem (that was already
solved separately by process isolation -- see embedding_worker_manager.py).

Design (deliberately asymmetric, matching the evidence):
  - BGE-M3 never touches the GPU and already protects its OWN startup via
    its own commit-headroom preflight (BGE_MIN_COMMIT_HEADROOM_MB). There
    is no measured scenario where Qwen's residency needs to be preempted to
    make room for BGE.
  - Qwen's *load* is the fragile operation. Before every LLM call, this
    manager checks whether Qwen is already resident (if so, nothing to do
    -- never preempt something that's already working) and, only if it is
    NOT resident and commit headroom is currently insufficient, stops the
    BGE worker and waits (bounded) for headroom to recover before letting
    the existing Ollama gateway attempt the call.
  - Preemption is entirely DEMAND-DRIVEN: there is no idle timer that stops
    BGE after N seconds of inactivity. BGE stays resident for as long as
    nothing needs the room. This avoids the "start worker -> embed one
    query -> stop worker -> next request -> start worker again" pattern
    the ~18-19s BGE cold-start time would make painful, without needing a
    separate idle-timeout subsystem.
  - This manager never hard-blocks a request: `ensure_llm_capacity` never
    raises. It does its best-effort preparation and returns; the actual
    Ollama call has its own existing, already-tested error handling
    (OllamaUnavailableError/ProviderExecutionError -> clean 503) as the
    real safety net if a load still fails despite this preparation.

Concurrency: a single lock serializes residency *decisions* (whether to
spawn/stop something), not the embed()/generate() calls themselves, so
throughput isn't serialized more than the existing architecture already
does. A best-effort active-job counter on the embedding worker (see
EmbeddingWorkerManager.get_active_job_count) prevents preempting BGE while
an embedding call is actually in flight. There is a narrow, accepted race
where a new embed() call could start in between that check and the actual
stop -- the worst outcome is that one embed() call has to pay a restart
(the existing crash-recovery path already handles "worker not ready,
restart it" gracefully), not a crash or lost data. A stricter cross-call
lock was deliberately not built for this: the existing containment
architecture already makes a spurious restart self-healing.
"""
import logging
import threading
import time
from enum import Enum
from typing import Dict, Optional

import httpx

from app.config import settings
from app.rag.embedding_worker_manager import get_worker_manager, WorkerStatus
from app.rag.resource_guard import get_memory_status

logger = logging.getLogger("sovereignx")


class ResourceState(str, Enum):
    NORMAL = "NORMAL"
    MEMORY_PRESSURE = "MEMORY_PRESSURE"
    TRANSITIONING = "TRANSITIONING"


def _log_transition(**fields) -> None:
    """Structured single-line log for every resource decision/transition."""
    kv = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info(f"resource_transition {kv}")


class ModelResourceManager:
    def __init__(self):
        self._transition_lock = threading.Lock()
        self._state = ResourceState.NORMAL

    # -- Ollama/Qwen residency introspection -----------------------------

    def is_qwen_resident(self) -> bool:
        """Reuses the existing OLLAMA_BASE_URL/MODEL_NAME config -- the same
        source of truth the gateway already uses, no separate config."""
        if not settings.MODEL_NAME:
            return False
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/ps")
            if res.status_code != 200:
                return False
            models = res.json().get("models", [])
            return any(m.get("model") == settings.MODEL_NAME or m.get("name") == settings.MODEL_NAME for m in models)
        except Exception as e:
            logger.warning(f"is_qwen_resident() check failed, assuming not resident: {e}")
            return False

    def unload_qwen(self) -> None:
        """
        Immediately unloads the configured LLM via Ollama's supported
        keep_alive=0 mechanism (no subprocess/CLI invocation). Implemented
        for completeness and available to future resource policy -- the
        current automatic flow never calls this, because the measured
        evidence shows no scenario where Qwen needs to be preempted to make
        room for BGE (BGE never touches the GPU and already protects its
        own startup independently).
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                    json={"model": settings.MODEL_NAME, "keep_alive": 0},
                )
            logger.info(f"resource_transition action=UNLOAD_QWEN model={settings.MODEL_NAME}")
        except Exception as e:
            logger.warning(f"Failed to request Qwen unload: {e}")

    # -- state introspection ----------------------------------------------

    def get_state(self) -> Dict:
        mem = get_memory_status()
        worker_status = get_worker_manager(settings.EMBEDDING_MODEL).get_status()
        return {
            "resource_state": self._state.value,
            "qwen_resident": self.is_qwen_resident(),
            "embedding_worker_status": worker_status["status"],
            "commit_headroom_mb": round(mem.commit_headroom_mb, 1),
        }

    # -- the core coordination call: before every LLM invocation ----------

    def ensure_llm_capacity(self) -> Dict[str, float]:
        """
        Best-effort preparation before invoking Qwen. Never raises -- the
        gateway's own error handling is the real safety net. Returns timing
        info (resource_wait_ms) to fold into the caller's existing latency
        instrumentation.
        """
        t0 = time.perf_counter()
        try:
            return self._ensure_llm_capacity_locked(t0)
        except Exception as e:
            # Genuinely never raise from here: a failure in the resource
            # orchestration must not block a chat request whose actual
            # safety net (the gateway's own OllamaUnavailableError handling)
            # is downstream of this call, not this method.
            logger.error(f"ensure_llm_capacity() failed unexpectedly, proceeding without intervention: {e}")
            return {"resource_wait_ms": (time.perf_counter() - t0) * 1000.0}

    def _ensure_llm_capacity_locked(self, t0: float) -> Dict[str, float]:
        with self._transition_lock:
            if self.is_qwen_resident():
                # Already loaded and working -- never preempt something
                # that's already fine, regardless of current headroom.
                _log_transition(embedding_worker="n/a", qwen="RESIDENT", action="none")
                return {"resource_wait_ms": 0.0}

            mem = get_memory_status()
            if mem.commit_headroom_mb >= settings.QWEN_MIN_COMMIT_HEADROOM_MB:
                _log_transition(
                    qwen="UNLOADED", action="none",
                    commit_headroom_mb=round(mem.commit_headroom_mb, 1),
                    threshold_mb=settings.QWEN_MIN_COMMIT_HEADROOM_MB,
                )
                return {"resource_wait_ms": 0.0}

            worker_mgr = get_worker_manager(settings.EMBEDDING_MODEL)
            active_jobs = worker_mgr.get_active_job_count()
            worker_status = worker_mgr.get_status()["status"]

            if active_jobs > 0:
                # An embedding call is actively in flight -- do not yank the
                # worker out from under it. Let the Ollama call attempt as-is;
                # its own error handling covers a genuine load failure.
                _log_transition(
                    action="SKIP_STOP_EMBEDDING_WORKER_BUSY", active_jobs=active_jobs,
                    commit_headroom_mb=round(mem.commit_headroom_mb, 1),
                )
                return {"resource_wait_ms": (time.perf_counter() - t0) * 1000.0}

            if worker_status in (WorkerStatus.NOT_STARTED.value, WorkerStatus.UNAVAILABLE_RESOURCES.value):
                # Nothing resident to stop.
                _log_transition(
                    action="NONE_WORKER_NOT_RESIDENT", worker_status=worker_status,
                    commit_headroom_mb=round(mem.commit_headroom_mb, 1),
                )
                return {"resource_wait_ms": (time.perf_counter() - t0) * 1000.0}

            self._state = ResourceState.TRANSITIONING
            headroom_before = mem.commit_headroom_mb
            _log_transition(
                action="STOP_EMBEDDING_WORKER_FOR_QWEN",
                commit_headroom_before_mb=round(headroom_before, 1),
                threshold_mb=settings.QWEN_MIN_COMMIT_HEADROOM_MB,
            )
            worker_mgr.shutdown()

            recovered, headroom_after = self._wait_for_commit_recovery(
                settings.QWEN_MIN_COMMIT_HEADROOM_MB, settings.RESOURCE_RELEASE_TIMEOUT_SECONDS
            )
            self._state = ResourceState.NORMAL if recovered else ResourceState.MEMORY_PRESSURE
            _log_transition(
                action="STOP_EMBEDDING_WORKER_FOR_QWEN_COMPLETE",
                commit_headroom_before_mb=round(headroom_before, 1),
                commit_headroom_after_mb=round(headroom_after, 1),
                recovered=recovered,
            )
            return {"resource_wait_ms": (time.perf_counter() - t0) * 1000.0}

    def _wait_for_commit_recovery(self, threshold_mb: float, timeout: float):
        deadline = time.time() + timeout
        mem = get_memory_status()
        poll_interval = 0.5
        while mem.commit_headroom_mb < threshold_mb and time.time() < deadline:
            time.sleep(poll_interval)
            mem = get_memory_status()
        return mem.commit_headroom_mb >= threshold_mb, mem.commit_headroom_mb

    # -- before embedding work: ensure the worker is available -------------

    def ensure_embedding_available(self, timeout: float) -> None:
        """
        Thin, lock-coordinated wrapper around the existing
        EmbeddingWorkerManager.ensure_ready() (which already has its own
        BGE-specific commit-headroom preflight -- reused here, not
        duplicated). The transition lock just prevents this from racing
        against ensure_llm_capacity()'s stop-BGE-for-Qwen sequence.
        """
        with self._transition_lock:
            get_worker_manager(settings.EMBEDDING_MODEL).ensure_ready(timeout)


_resource_manager_lock = threading.Lock()
_resource_manager: Optional[ModelResourceManager] = None


def get_resource_manager() -> ModelResourceManager:
    global _resource_manager
    with _resource_manager_lock:
        if _resource_manager is None:
            _resource_manager = ModelResourceManager()
        return _resource_manager


def reset_resource_manager_for_testing():
    global _resource_manager
    with _resource_manager_lock:
        _resource_manager = None
