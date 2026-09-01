"""
Owns the lifecycle of the isolated BGE-M3 embedding worker process.

This is the CONTAINMENT boundary described in the investigation: BGE-M3's
native (PyTorch) execution is proven to be able to SIGSEGV under Windows
commit-charge pressure, independent of package versions. By running it in
a separate OS process (spawned via multiprocessing's Windows-safe 'spawn'
context, never 'fork'), a crash there terminates only that subprocess --
the parent FastAPI process has its own address space and survives,
observes the failure, and can respond with a clean, recoverable
EmbeddingModelUnavailableError instead of dying itself.

A Windows commit-headroom preflight (resource_guard.get_memory_status)
runs before every spawn/restart and before every embed() call. This is
PREVENTION, reducing how often the worker is asked to do something known
to be risky -- it is not, and cannot be, a guarantee: memory conditions
can change between the check and the actual call. The guarantee that a
native crash cannot take down FastAPI comes entirely from the process
boundary itself, not from this check.
"""
import logging
import multiprocessing
import os
import queue
import threading
import time
import uuid
from enum import Enum
from typing import Dict, List, Optional

from app.config import settings
from app.rag.exceptions import EmbeddingModelUnavailableError
from app.rag.resource_guard import get_memory_status

logger = logging.getLogger("sovereignx")


class WorkerStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    STARTING = "STARTING"
    READY = "READY"
    UNAVAILABLE_RESOURCES = "UNAVAILABLE_RESOURCES"
    CRASHED = "CRASHED"
    RESTARTING = "RESTARTING"


class EmbeddingWorkerManager:
    def __init__(self, model_name: str, worker_target=None, provider: str = "bge"):
        self.model_name = model_name
        # "bge" | "e5" -- selects which model runner run_worker() constructs
        # inside the child process, and which commit-headroom threshold this
        # manager's own preflight checks use (see _threshold_mb below).
        self.provider = provider
        # Test-only injection point: lets tests substitute a lightweight
        # fake worker function (e.g. one that can be told to os._exit()
        # on command) instead of spawning the real model loader, so crash
        # detection/restart logic can be tested fast and deterministically
        # without depending on the real model or real memory exhaustion.
        # Production code always uses the default (the real run_worker).
        self._worker_target = worker_target
        self._ctx = multiprocessing.get_context("spawn")
        self._process = None
        self._request_queue = None
        self._response_queue = None
        self._status = WorkerStatus.NOT_STARTED
        self._worker_pid: Optional[int] = None
        self._lock = threading.RLock()  # serializes lifecycle + IPC round-trips
        self._restart_timestamps: List[float] = []
        self._last_error: Optional[str] = None
        # Best-effort hint (not a strict guarantee) for ModelResourceManager:
        # lets it avoid preempting the worker while an embed() call is
        # actually in flight. A GIL-atomic int is sufficient here -- see
        # ModelResourceManager's module docstring for the accepted narrow
        # race and why it self-heals rather than needing a stricter lock.
        self._active_jobs = 0

    def _threshold_mb(self) -> float:
        return settings.BGE_MIN_COMMIT_HEADROOM_MB if self.provider == "bge" else settings.E5_MIN_COMMIT_HEADROOM_MB

    # -- status/introspection ------------------------------------------

    def get_status(self) -> dict:
        with self._lock:
            return {
                "status": self._status.value,
                "worker_pid": self._worker_pid,
                "manager_pid": os.getpid(),
                "last_error": self._last_error,
            }

    def get_active_job_count(self) -> int:
        return self._active_jobs

    # -- lifecycle --------------------------------------------------------

    def ensure_ready(self, timeout: float) -> None:
        """Spawns the worker if not already alive and ready. Raises
        EmbeddingModelUnavailableError if resources are unsafe or startup fails."""
        with self._lock:
            if self._status == WorkerStatus.READY and self._process is not None and self._process.is_alive():
                return
            self._spawn_if_safe(timeout)

    def _spawn_if_safe(self, timeout: float) -> None:
        mem = get_memory_status(self._threshold_mb())
        if not mem.safe_for_embedding:
            self._status = WorkerStatus.UNAVAILABLE_RESOURCES
            self._last_error = (
                f"insufficient_commit_headroom: {mem.commit_headroom_mb:.0f}MB available, "
                f"{mem.threshold_mb:.0f}MB required"
            )
            logger.warning(
                f"{self.provider} worker spawn skipped -- unsafe resource condition "
                f"(commit_headroom_mb={mem.commit_headroom_mb:.0f} threshold_mb={mem.threshold_mb:.0f} "
                f"available_ram_mb={mem.available_physical_mb:.0f} source={mem.source})"
            )
            raise EmbeddingModelUnavailableError(
                "Local embedding model is temporarily unavailable: insufficient system memory headroom "
                f"({mem.commit_headroom_mb:.0f}MB free, {mem.threshold_mb:.0f}MB safety margin required)."
            )

        self._status = WorkerStatus.STARTING
        self._request_queue = self._ctx.Queue()
        self._response_queue = self._ctx.Queue()

        if self._worker_target is not None:
            target = self._worker_target
        else:
            from app.rag.embedding_worker import run_worker
            target = run_worker
        self._process = self._ctx.Process(
            target=target,
            args=(self._request_queue, self._response_queue, self.model_name, self.provider),
            daemon=True,
        )
        manager_pid = os.getpid()
        self._process.start()
        logger.info(
            f"{self.provider} embedding worker spawn requested. FASTAPI_PID={manager_pid} "
            f"EMBEDDING_WORKER_PID={self._process.pid}"
        )

        try:
            msg = self._response_queue.get(timeout=timeout)
        except queue.Empty:
            self._status = WorkerStatus.CRASHED
            self._last_error = "worker did not report ready within startup timeout"
            logger.error(
                f"{self.provider} embedding worker (PID={self._process.pid}) failed to become ready "
                f"within {timeout}s; terminating."
            )
            self._terminate_process()
            raise EmbeddingModelUnavailableError(
                "Local embedding model worker failed to start within the configured timeout."
            )

        if msg.get("type") == "ready":
            self._worker_pid = msg.get("pid")
            self._status = WorkerStatus.READY
            self._last_error = None
            logger.info(
                f"{self.provider} embedding worker READY. FASTAPI_PID={manager_pid} EMBEDDING_WORKER_PID={self._worker_pid}"
            )
        else:
            self._status = WorkerStatus.CRASHED
            self._last_error = msg.get("error", "unknown init failure")
            logger.error(f"{self.provider} embedding worker failed to initialize: {self._last_error}")
            self._terminate_process()
            raise EmbeddingModelUnavailableError(
                f"Local embedding model failed to initialize: {self._last_error}"
            )

    def _terminate_process(self) -> None:
        if self._process is not None:
            try:
                if self._process.is_alive():
                    self._process.terminate()
                    self._process.join(timeout=5)
            except Exception as e:
                logger.warning(f"Error terminating BGE embedding worker process: {e}")
        self._process = None
        self._request_queue = None
        self._response_queue = None
        self._worker_pid = None

    def shutdown(self) -> None:
        """Clean shutdown -- call on FastAPI application shutdown to avoid an orphaned worker process."""
        with self._lock:
            if self._process is not None and self._process.is_alive():
                try:
                    self._request_queue.put({"op": "shutdown"})
                    self._process.join(timeout=5)
                except Exception:
                    pass
            self._terminate_process()
            self._status = WorkerStatus.NOT_STARTED

    # -- embedding calls --------------------------------------------------

    def embed(self, texts: List[str]) -> List[List[float]]:
        with self._lock:
            mem = get_memory_status(self._threshold_mb())
            if not mem.safe_for_embedding:
                self._status = WorkerStatus.UNAVAILABLE_RESOURCES
                logger.warning(
                    f"{self.provider} embed() refused -- unsafe resource condition "
                    f"(commit_headroom_mb={mem.commit_headroom_mb:.0f} threshold_mb={mem.threshold_mb:.0f} "
                    f"available_ram_mb={mem.available_physical_mb:.0f})"
                )
                raise EmbeddingModelUnavailableError(
                    "Local embedding model is temporarily unavailable: insufficient system memory headroom "
                    f"({mem.commit_headroom_mb:.0f}MB free, {mem.threshold_mb:.0f}MB safety margin required)."
                )

            if self._status != WorkerStatus.READY or self._process is None or not self._process.is_alive():
                self._attempt_restart()

            request_id = str(uuid.uuid4())
            self._active_jobs += 1
            try:
                self._request_queue.put({"request_id": request_id, "op": "embed", "texts": texts})

                try:
                    msg = self._response_queue.get(timeout=settings.BGE_WORKER_TIMEOUT_SECONDS)
                except queue.Empty:
                    if not self._process.is_alive():
                        self._handle_crash("worker process died (no response, process not alive)")
                        raise EmbeddingModelUnavailableError(
                            "Local embedding model worker crashed while processing this request."
                        )
                    raise EmbeddingModelUnavailableError(
                        "Local embedding model worker timed out processing this request."
                    )

                if msg.get("request_id") != request_id:
                    logger.warning("Discarding stale response from BGE embedding worker (mismatched request_id).")
                    raise EmbeddingModelUnavailableError("Local embedding model returned an unexpected response.")

                if msg.get("status") != "ok":
                    raise EmbeddingModelUnavailableError(
                        f"Local embedding model failed: {msg.get('error', 'unknown error')}"
                    )

                return msg["vectors"]
            finally:
                self._active_jobs -= 1

    def _handle_crash(self, reason: str) -> None:
        exitcode = self._process.exitcode if self._process is not None else None
        logger.error(
            f"{self.provider} embedding worker crash detected: {reason} (PID={self._worker_pid}, exitcode={exitcode})"
        )
        self._status = WorkerStatus.CRASHED
        self._last_error = reason
        self._terminate_process()

    def _attempt_restart(self) -> None:
        """Bounded restart: limited attempts within a cooldown window, to
        avoid a crash/restart loop hammering an already-unsafe machine."""
        now = time.time()
        window = settings.BGE_WORKER_RESTART_COOLDOWN_SECONDS * settings.BGE_WORKER_MAX_RESTART_ATTEMPTS
        self._restart_timestamps = [t for t in self._restart_timestamps if now - t < window]

        if len(self._restart_timestamps) >= settings.BGE_WORKER_MAX_RESTART_ATTEMPTS:
            self._status = WorkerStatus.CRASHED
            logger.error(
                f"{self.provider} embedding worker restart limit reached "
                f"({settings.BGE_WORKER_MAX_RESTART_ATTEMPTS} attempts within {window:.0f}s) -- not restarting."
            )
            raise EmbeddingModelUnavailableError(
                "Local embedding model worker has crashed repeatedly and will not be restarted "
                "until resource conditions stabilize."
            )

        if self._restart_timestamps:
            elapsed = now - self._restart_timestamps[-1]
            if elapsed < settings.BGE_WORKER_RESTART_COOLDOWN_SECONDS:
                sleep_for = settings.BGE_WORKER_RESTART_COOLDOWN_SECONDS - elapsed
                logger.info(f"{self.provider} embedding worker restart cooldown: waiting {sleep_for:.1f}s")
                time.sleep(sleep_for)

        self._status = WorkerStatus.RESTARTING
        self._restart_timestamps.append(time.time())
        logger.info(
            f"Restarting {self.provider} embedding worker (attempt {len(self._restart_timestamps)}"
            f"/{settings.BGE_WORKER_MAX_RESTART_ATTEMPTS})"
        )
        self._spawn_if_safe(timeout=settings.BGE_WORKER_STARTUP_TIMEOUT_SECONDS)


_manager_lock = threading.Lock()
_managers: Dict[str, "EmbeddingWorkerManager"] = {}


def get_worker_manager(provider: str, model_name: str) -> EmbeddingWorkerManager:
    """
    Process-wide singleton accessor for the embedding worker manager, keyed
    by provider ("bge" | "e5") so both can have their own independent
    worker/registry entry -- needed for Phase 3's "switch without code
    changes" requirement (BGE remains available as a fallback even while E5
    is active) and for A/B measuring both providers side by side.
    """
    global _managers
    with _manager_lock:
        if provider not in _managers:
            _managers[provider] = EmbeddingWorkerManager(model_name, provider=provider)
        return _managers[provider]


def reset_worker_manager_for_testing():
    """Test-only. Does not terminate a live process -- call shutdown() on
    the existing manager(s) first if one may be running."""
    global _managers
    with _manager_lock:
        _managers = {}
