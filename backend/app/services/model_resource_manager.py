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

Design:
  - BGE-M3 never touches the GPU and already protects its OWN startup via
    its own commit-headroom preflight (BGE_MIN_COMMIT_HEADROOM_MB).
  - Before every LLM call, `ensure_llm_capacity` checks whether Qwen is
    already resident (if so, nothing to do -- never preempt something
    that's already working) and, only if it is NOT resident and commit
    headroom is currently insufficient, stops the BGE worker and waits
    (bounded) for headroom to recover before letting the existing Ollama
    gateway attempt the call.
  - The reverse direction, `ensure_embedding_capacity`, is symmetric: before
    a DOCUMENT_RAG retrieval, if BGE is not already ready and headroom is
    insufficient *because Qwen is resident*, it stops Qwen (via Ollama's
    keep_alive=0) and waits for headroom to recover before starting BGE.
    Both directions were originally measured as asymmetric (an earlier
    investigation found no scenario requiring Qwen->BGE preemption on this
    dev machine), but a later live benchmark proved the reverse case DOES
    happen in practice -- a second consecutive DOCUMENT_RAG turn, after the
    first turn loaded Qwen, would otherwise find BGE permanently unable to
    start. Unlike `ensure_llm_capacity` (which never raises -- a GENERAL_CHAT
    answer is always an acceptable fallback), `ensure_embedding_capacity`
    DOES raise `EmbeddingModelUnavailableError` if BGE still cannot be made
    available: DOCUMENT_RAG is only ever selected for an explicit,
    deliberate document request (see chat/routing.py), so silently
    answering as GENERAL_CHAT instead would be an ungrounded answer
    presented as if grounding had succeeded -- see chat/service.py's
    _retrieve_for_document_rag for how callers must treat this.
  - Preemption in BOTH directions is entirely DEMAND-DRIVEN: there is no
    idle timer that stops either model after N seconds of inactivity, and
    if headroom is already sufficient for both to coexist (larger-RAM
    production hardware), NO transition happens at all in either direction
    -- this code does not assume the dev laptop's constraints define
    production behavior.
  - This manager never hard-blocks on a resource-orchestration failure: any
    unexpected internal error in either method is caught, logged, and
    treated as "proceed without intervention" -- the real safety nets
    (Ollama gateway's OllamaUnavailableError handling, and the explicit
    document_grounding_unavailable state for RAG) are downstream of this
    module, not inside it.

Concurrency: a single lock serializes residency *decisions* (whether to
spawn/stop something) in both directions, not the embed()/generate() calls
themselves, so throughput isn't serialized more than the existing
architecture already does. Two best-effort active-job counters -- one on
the embedding worker (EmbeddingWorkerManager.get_active_job_count) and one
here for Qwen (mark_qwen_call_start/_end) -- prevent either direction from
preempting a model while it is actually mid-call: `ensure_llm_capacity`
won't stop BGE while an embed() is in flight, and `ensure_embedding_capacity`
won't stop Qwen while a chat_completion()/stream_chat_completion() is in
flight for another concurrent request. There is a narrow, accepted race
where a new call could start in between that check and the actual stop --
the worst outcome is that call has to pay a restart/retry (the existing
crash-recovery path already handles "worker not ready, restart it"
gracefully for BGE; a concurrent generation request that started a moment
after the check would simply get its own fresh Ollama load), not a crash or
lost data. A stricter cross-call lock was deliberately not built for this:
the existing containment architecture already makes a spurious restart
self-healing.
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
from app.rag.exceptions import EmbeddingModelUnavailableError

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
        # Best-effort hint (not a strict guarantee), symmetric to
        # EmbeddingWorkerManager._active_jobs -- lets ensure_embedding_capacity
        # avoid unloading Qwen while a generation call is actually in flight
        # for another concurrent request. GIL-atomic int; see module
        # docstring for the accepted narrow race and why it self-heals.
        self._qwen_active_jobs = 0

    def mark_qwen_call_start(self) -> None:
        self._qwen_active_jobs += 1

    def mark_qwen_call_end(self) -> None:
        self._qwen_active_jobs -= 1

    # -- provider-awareness (Phase 13 of the E5 migration) -----------------
    #
    # All the BGE<->Qwen preemption logic below exists because BGE-M3 always
    # runs as a separate OS process (mandatory, for native-crash isolation --
    # see embedding_worker_manager.py) with its own ~1.9GB resident
    # footprint competing for the same Windows commit headroom Qwen needs.
    # multilingual-e5-small does NOT need that isolation (measured stable
    # in-process across this migration's benchmarking -- see
    # embeddings.py's _E5SmallModelRunner docstring) and, in its default
    # configuration, has no separate process at all: there is nothing to
    # preempt in either direction, so E5 and Qwen simply coexist. These
    # three helpers are the ONLY place that branches on EMBEDDING_PROVIDER --
    # chat/service.py and the rest of the app stay provider-agnostic.

    def _embedding_worker_is_active(self) -> bool:
        """True only if the active embedding provider runs as a separate OS
        process this manager might need to coordinate residency for."""
        if settings.EMBEDDING_PROVIDER == "bge":
            return True
        return settings.E5_USE_ISOLATED_WORKER

    def _active_model_name(self) -> str:
        return settings.EMBEDDING_MODEL if settings.EMBEDDING_PROVIDER == "bge" else settings.E5_EMBEDDING_MODEL

    def _active_threshold_mb(self) -> float:
        return settings.BGE_MIN_COMMIT_HEADROOM_MB if settings.EMBEDDING_PROVIDER == "bge" else settings.E5_MIN_COMMIT_HEADROOM_MB

    def _active_worker_manager(self):
        return get_worker_manager(settings.EMBEDDING_PROVIDER, self._active_model_name())

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
        keep_alive=0 mechanism (no subprocess/CLI invocation). Called by
        ensure_embedding_capacity() when BGE needs the room and Qwen is
        the thing occupying it -- see that method and the module docstring.
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
        if self._embedding_worker_is_active():
            embedding_worker_status = self._active_worker_manager().get_status()["status"]
        else:
            # In-process E5: no worker process/status to report -- reflect
            # background-warmup readiness instead (see app/services/readiness.py).
            from app.services import readiness
            embedding_worker_status = "READY" if readiness.get_state().embedding_ready else "IN_PROCESS_NOT_READY"
        return {
            "resource_state": self._state.value,
            "qwen_resident": self.is_qwen_resident(),
            "embedding_worker_status": embedding_worker_status,
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

            if not self._embedding_worker_is_active():
                # Current embedding provider (E5, in-process by default) has
                # no separate worker process to stop -- nothing to preempt.
                # Measured safe to let Qwen's own load attempt proceed as-is
                # (see Phase 10/21 coexistence evidence in the migration report).
                _log_transition(
                    action="NONE_EMBEDDING_PROVIDER_IN_PROCESS_NO_WORKER_TO_PREEMPT",
                    embedding_provider=settings.EMBEDDING_PROVIDER,
                    commit_headroom_mb=round(mem.commit_headroom_mb, 1),
                )
                return {"resource_wait_ms": (time.perf_counter() - t0) * 1000.0}

            worker_mgr = self._active_worker_manager()
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

        Used for document INDEXING (api/rag.py), where there is no
        "explicit user request must not silently degrade" concern -- an
        indexing failure already has its own clean error handling upstream.
        Chat's DOCUMENT_RAG retrieval path uses ensure_embedding_capacity()
        instead, which additionally attempts the reverse Qwen->BGE
        preemption before giving up.
        """
        with self._transition_lock:
            if not self._embedding_worker_is_active():
                from app.rag.embeddings import get_embedding_provider
                get_embedding_provider().initialize()
                return
            self._active_worker_manager().ensure_ready(timeout)

    def ensure_embedding_capacity(self, timeout: float) -> None:
        """
        Best-effort preparation before a DOCUMENT_RAG retrieval: ensures BGE
        is ready, performing the reverse (Qwen -> BGE) resource transition
        if -- and only if -- it's actually needed (demand-driven, same
        policy as ensure_llm_capacity's BGE -> Qwen direction: if BGE is
        already ready, or headroom is already sufficient for both, no
        transition happens at all).

        Unlike ensure_llm_capacity, this method DOES let
        EmbeddingModelUnavailableError propagate if BGE genuinely cannot be
        made available (even after attempting the reverse transition) --
        callers (chat/service.py's _retrieve_for_document_rag) must treat
        that as "document grounding unavailable" and return an explicit
        failure state, never a silent GENERAL_CHAT-looking answer, since
        DOCUMENT_RAG is only ever selected for an explicit document request.
        """
        with self._transition_lock:
            if not self._embedding_worker_is_active():
                # In-process E5: nothing to "make ready" via worker
                # machinery, and no Qwen preemption needed or possible --
                # measured-safe coexistence (see Phase 10/21 evidence in the
                # migration report). Just ensure the in-process singleton is
                # warm; EmbeddingModelUnavailableError still propagates
                # naturally from initialize() on genuine failure.
                _log_transition(
                    action="NONE_EMBEDDING_PROVIDER_IN_PROCESS_ENSURE_WARM",
                    embedding_provider=settings.EMBEDDING_PROVIDER,
                )
                from app.rag.embeddings import get_embedding_provider
                get_embedding_provider().initialize()
                return

            worker_mgr = self._active_worker_manager()

            if worker_mgr.get_status()["status"] == WorkerStatus.READY.value:
                # Cheap common-case fast path -- but the cached status can be
                # stale (the worker may have died since it was last checked,
                # e.g. reaped under the same memory pressure this whole
                # module exists to manage). Don't just propagate a failure
                # here: fall through to the full decision tree below, which
                # can still attempt the reverse Qwen->BGE preemption before
                # giving up. This is exactly what closes the gap a live
                # benchmark found -- a stale-READY status must never skip
                # the recovery attempt.
                try:
                    _log_transition(action="NONE_EMBEDDING_ALREADY_READY")
                    worker_mgr.ensure_ready(timeout)
                    return
                except EmbeddingModelUnavailableError:
                    _log_transition(action="EMBEDDING_STATUS_STALE_RETRYING_FULL_CHECK")

            mem = get_memory_status()
            if mem.commit_headroom_mb >= self._active_threshold_mb():
                # Sufficient headroom already -- start the embedding worker
                # normally, no preemption needed. The common case on
                # hardware with enough RAM for both models resident at once.
                _log_transition(
                    action="START_EMBEDDING_NO_PREEMPTION_NEEDED",
                    commit_headroom_mb=round(mem.commit_headroom_mb, 1),
                )
                worker_mgr.ensure_ready(timeout)
                return

            if not self.is_qwen_resident():
                # Insufficient headroom, but nothing to preempt -- some
                # other process is consuming the memory. Let ensure_ready's
                # own preflight raise its normal, already-tested error.
                _log_transition(
                    action="EMBEDDING_UNAVAILABLE_NO_QWEN_TO_PREEMPT",
                    commit_headroom_mb=round(mem.commit_headroom_mb, 1),
                )
                worker_mgr.ensure_ready(timeout)
                return

            if self._qwen_active_jobs > 0:
                # A generation call is actively in flight for another
                # request -- do not yank Qwen out from under it. Let
                # ensure_ready's own preflight decide (will likely still
                # fail, surfacing the real "document grounding unavailable"
                # state rather than corrupting a concurrent generation).
                _log_transition(
                    action="SKIP_STOP_QWEN_BUSY",
                    active_jobs=self._qwen_active_jobs,
                    commit_headroom_mb=round(mem.commit_headroom_mb, 1),
                )
                worker_mgr.ensure_ready(timeout)
                return

            self._state = ResourceState.TRANSITIONING
            headroom_before = mem.commit_headroom_mb
            _log_transition(
                action="STOP_QWEN_FOR_EMBEDDING",
                commit_headroom_before_mb=round(headroom_before, 1),
                threshold_mb=self._active_threshold_mb(),
            )
            self.unload_qwen()

            recovered, headroom_after = self._wait_for_commit_recovery(
                self._active_threshold_mb(), settings.RESOURCE_RELEASE_TIMEOUT_SECONDS
            )
            self._state = ResourceState.NORMAL if recovered else ResourceState.MEMORY_PRESSURE
            _log_transition(
                action="STOP_QWEN_FOR_EMBEDDING_COMPLETE",
                commit_headroom_before_mb=round(headroom_before, 1),
                commit_headroom_after_mb=round(headroom_after, 1),
                recovered=recovered,
            )
            # Whichever way recovery went, let ensure_ready's own preflight
            # make the final call -- it re-checks headroom itself, so this
            # doesn't duplicate the safety check or risk drifting from it.
            worker_mgr.ensure_ready(timeout)


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
