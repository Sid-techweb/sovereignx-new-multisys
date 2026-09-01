import time
import unittest
from unittest.mock import patch

from app.config import settings
from app.rag.embedding_worker_manager import EmbeddingWorkerManager, WorkerStatus
from app.rag.resource_guard import MemoryStatus
from app.rag.exceptions import EmbeddingModelUnavailableError

TEST_MODEL_NAME = "fake-model-for-tests"


# --- Fake worker targets -----------------------------------------------
# These stand in for the real BGE-M3 loader (app/rag/embedding_worker.run_worker)
# so crash/timeout/restart logic can be tested fast and deterministically,
# without depending on the real model or real memory exhaustion. They are
# module-level functions (required for multiprocessing 'spawn' picklability).

def fake_worker_ready_then_echo(request_queue, response_queue, model_name, provider="bge"):
    """Reports ready immediately, then echoes a fixed fake vector per text."""
    import os
    response_queue.put({"type": "ready", "pid": os.getpid()})
    while True:
        job = request_queue.get()
        if job is None or job.get("op") == "shutdown":
            break
        texts = job.get("texts", [])
        response_queue.put({
            "request_id": job["request_id"],
            "status": "ok",
            "vectors": [[0.1, 0.2, 0.3] for _ in texts],
        })


def fake_worker_init_failure(request_queue, response_queue, model_name, provider="bge"):
    import os
    response_queue.put({"type": "init_failed", "pid": os.getpid(), "error": "simulated init failure"})


def fake_worker_never_responds_to_job(request_queue, response_queue, model_name, provider="bge"):
    """Reports ready, then hangs forever on any embed job -- simulates a stuck (not crashed) worker."""
    import os
    response_queue.put({"type": "ready", "pid": os.getpid()})
    while True:
        job = request_queue.get()
        if job is None or job.get("op") == "shutdown":
            break
        time.sleep(60)


def _make_unsafe_status():
    return MemoryStatus(
        available_physical_mb=1000.0,
        committed_mb=26000.0,
        commit_limit_mb=27000.0,
        commit_headroom_mb=500.0,
        safe_for_embedding=False,
        threshold_mb=settings.BGE_MIN_COMMIT_HEADROOM_MB,
        source="windows_commit_charge",
    )


def _make_safe_status():
    return MemoryStatus(
        available_physical_mb=6000.0,
        committed_mb=20000.0,
        commit_limit_mb=27000.0,
        commit_headroom_mb=7000.0,
        safe_for_embedding=True,
        threshold_mb=settings.BGE_MIN_COMMIT_HEADROOM_MB,
        source="windows_commit_charge",
    )


class TestEmbeddingWorkerManager(unittest.TestCase):
    def setUp(self):
        self._managers_to_shutdown = []

    def tearDown(self):
        for m in self._managers_to_shutdown:
            try:
                m.shutdown()
            except Exception:
                pass

    def _new_manager(self, worker_target):
        m = EmbeddingWorkerManager(TEST_MODEL_NAME, worker_target=worker_target)
        self._managers_to_shutdown.append(m)
        return m

    # --- Initialization / PID isolation ---------------------------------

    @patch("app.rag.embedding_worker_manager.get_memory_status", return_value=_make_safe_status())
    def test_worker_initializes_in_separate_process(self, mock_mem):
        import os
        manager = self._new_manager(fake_worker_ready_then_echo)
        manager.ensure_ready(timeout=15)

        status = manager.get_status()
        self.assertEqual(status["status"], WorkerStatus.READY.value)
        self.assertIsNotNone(status["worker_pid"])
        self.assertNotEqual(status["worker_pid"], os.getpid())

    @patch("app.rag.embedding_worker_manager.get_memory_status", return_value=_make_safe_status())
    def test_worker_successful_embedding(self, mock_mem):
        manager = self._new_manager(fake_worker_ready_then_echo)
        vectors = manager.embed(["hello", "world"])
        self.assertEqual(len(vectors), 2)
        self.assertEqual(vectors[0], [0.1, 0.2, 0.3])

    @patch("app.rag.embedding_worker_manager.get_memory_status", return_value=_make_safe_status())
    def test_worker_init_failure_raises_recoverable_error(self, mock_mem):
        manager = self._new_manager(fake_worker_init_failure)
        with self.assertRaises(EmbeddingModelUnavailableError):
            manager.ensure_ready(timeout=15)
        self.assertEqual(manager.get_status()["status"], WorkerStatus.CRASHED.value)

    # --- Crash detection + transparent restart --------------------------

    @patch("app.rag.embedding_worker_manager.get_memory_status", return_value=_make_safe_status())
    def test_worker_crash_detected_and_transparently_restarts(self, mock_mem):
        with patch.object(settings, "BGE_WORKER_TIMEOUT_SECONDS", 5), \
             patch.object(settings, "BGE_WORKER_RESTART_COOLDOWN_SECONDS", 0.1), \
             patch.object(settings, "BGE_WORKER_MAX_RESTART_ATTEMPTS", 3):
            manager = self._new_manager(fake_worker_ready_then_echo)
            manager.ensure_ready(timeout=15)
            first_pid = manager.get_status()["worker_pid"]

            # Intentionally terminate the worker to simulate a native crash,
            # without requiring actual memory exhaustion or a real SIGSEGV.
            manager._process.kill()
            manager._process.join(timeout=5)

            vectors = manager.embed(["hello after crash"])

            self.assertEqual(len(vectors), 1)
            second_pid = manager.get_status()["worker_pid"]
            self.assertNotEqual(first_pid, second_pid)
            self.assertEqual(manager.get_status()["status"], WorkerStatus.READY.value)

    # --- Timeout (worker alive but unresponsive) ------------------------

    @patch("app.rag.embedding_worker_manager.get_memory_status", return_value=_make_safe_status())
    def test_worker_timeout_raises_without_restarting(self, mock_mem):
        with patch.object(settings, "BGE_WORKER_TIMEOUT_SECONDS", 1):
            manager = self._new_manager(fake_worker_never_responds_to_job)
            manager.ensure_ready(timeout=15)

            with self.assertRaises(EmbeddingModelUnavailableError) as ctx:
                manager.embed(["this will hang"])
            self.assertIn("timed out", str(ctx.exception).lower())
            # A mere timeout is not a crash -- the (hung) process is still alive,
            # and we should not have torn it down just because one call was slow.
            self.assertTrue(manager._process.is_alive())

    # --- Restart-loop protection (fast, logic-level) ---------------------

    def test_restart_loop_protection_stops_after_max_attempts(self):
        manager = self._new_manager(fake_worker_ready_then_echo)
        with patch.object(settings, "BGE_WORKER_MAX_RESTART_ATTEMPTS", 2), \
             patch.object(settings, "BGE_WORKER_RESTART_COOLDOWN_SECONDS", 0.01):
            now = time.time()
            manager._restart_timestamps = [now, now]  # already at the limit
            with patch.object(manager, "_spawn_if_safe") as mock_spawn:
                with self.assertRaises(EmbeddingModelUnavailableError) as ctx:
                    manager._attempt_restart()
                mock_spawn.assert_not_called()
                self.assertIn("will not be restarted", str(ctx.exception))

    # --- Resource preflight ----------------------------------------------

    @patch("app.rag.embedding_worker_manager.get_memory_status", return_value=_make_unsafe_status())
    def test_unsafe_resources_blocks_spawn_without_touching_bge(self, mock_mem):
        manager = self._new_manager(fake_worker_ready_then_echo)
        with self.assertRaises(EmbeddingModelUnavailableError) as ctx:
            manager.ensure_ready(timeout=15)
        self.assertIn("memory headroom", str(ctx.exception))
        self.assertEqual(manager.get_status()["status"], WorkerStatus.UNAVAILABLE_RESOURCES.value)
        self.assertIsNone(manager._process)  # never spawned

    @patch("app.rag.embedding_worker_manager.get_memory_status", return_value=_make_unsafe_status())
    def test_unsafe_resources_blocks_embed_even_if_worker_was_ready(self, mock_mem):
        # Simulate: worker previously became ready under safe conditions, but
        # resources are unsafe *now* -- embed() must still refuse.
        manager = self._new_manager(fake_worker_ready_then_echo)
        manager._status = WorkerStatus.READY
        with self.assertRaises(EmbeddingModelUnavailableError) as ctx:
            manager.embed(["should be blocked"])
        self.assertIn("memory headroom", str(ctx.exception))


class TestGeneralChatUnaffectedByEmbeddingWorker(unittest.TestCase):
    """GENERAL_CHAT must keep working even if the embedding worker is
    crashed/unavailable -- it never touches BGE-M3 at all."""

    @patch("app.rag.embedding_worker_manager.get_worker_manager")
    def test_general_chat_never_calls_worker_manager(self, mock_get_manager):
        mock_get_manager.side_effect = AssertionError(
            "GENERAL_CHAT must not touch the embedding worker manager"
        )
        from app.chat.routing import classify_route, ChatRoute
        # Sanity: this question routes GENERAL_CHAT and the chat service's
        # retrieval branch (the only caller of get_worker_manager in the
        # chat path) is never entered for it -- see test_chat.py's
        # test_general_chat_answers_without_documents / no_external_search
        # for the full request-level proof; this asserts the routing
        # decision itself, which gates whether that call site is reached.
        self.assertEqual(classify_route("What is machine learning?"), ChatRoute.GENERAL_CHAT)


class TestSingleEmbeddingArchitecture(unittest.TestCase):
    """
    Document ingestion and query embedding must go through the SAME
    provider (whichever EMBEDDING_PROVIDER currently selects -- see
    app.rag.embeddings.get_embedding_provider) -- there must be one
    embedding execution architecture, not a different provider for
    indexing than for retrieval. Checks the current default's actual type
    rather than hardcoding BGE, since which provider is default is itself
    a config choice (E5 since the embedding migration; BGE remains fully
    supported as a fallback -- see TestBGEFallbackStillWorks in
    test_e5_embedding_migration.py for that path specifically).
    """

    def test_indexer_and_retriever_default_to_the_same_provider_type(self):
        from unittest.mock import MagicMock
        from app.rag.indexer import KnowledgeBaseIndexer
        from app.rag.retriever import KnowledgeBaseRetriever
        from app.rag.embeddings import get_embedding_provider
        indexer = KnowledgeBaseIndexer(MagicMock())
        retriever = KnowledgeBaseRetriever(MagicMock())
        expected_type = type(get_embedding_provider())
        self.assertIsInstance(indexer.embedding_provider, expected_type)
        self.assertIsInstance(retriever.embedding_provider, expected_type)


class TestHealthAfterWorkerCrash(unittest.TestCase):
    """API-contract level: /health and /models must stay correct and
    responsive when the embedding worker is in a crashed state. (The
    stronger, process-level guarantee -- that a real BGE-M3 SIGSEGV cannot
    take the FastAPI OS process down at all -- is a cross-process property
    verified via a live, two-PID manual test, not an in-process unit test.)"""

    def test_health_and_models_respond_when_worker_crashed(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.rag import embedding_worker_manager as ewm

        # Registered under whichever provider is CURRENTLY active (not
        # hardcoded "bge") -- /models looks up settings.EMBEDDING_PROVIDER's
        # worker manager, and which provider is default is itself a config
        # choice (E5 since the embedding migration; see get_worker_manager()'s
        # docstring -- the registry is keyed by provider so BGE stays
        # available as a fallback alongside E5).
        fake_manager = EmbeddingWorkerManager(
            TEST_MODEL_NAME, worker_target=fake_worker_ready_then_echo, provider=settings.EMBEDDING_PROVIDER
        )
        fake_manager._status = WorkerStatus.CRASHED
        fake_manager._last_error = "simulated crash for health check"

        original_managers = ewm._managers
        ewm._managers = {**original_managers, settings.EMBEDDING_PROVIDER: fake_manager}
        try:
            client = TestClient(app, headers={"X-API-Key": settings.API_KEY})
            res = client.get("/health")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "ok")

            res2 = client.get("/models")
            self.assertEqual(res2.status_code, 200)
            self.assertEqual(res2.json()["embedding_worker_status"], "CRASHED")
        finally:
            ewm._managers = original_managers


if __name__ == "__main__":
    unittest.main()
