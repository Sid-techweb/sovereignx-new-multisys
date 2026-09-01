import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from app.config import settings
from app.services.model_resource_manager import ModelResourceManager, ResourceState
from app.rag.embedding_worker_manager import WorkerStatus
from app.rag.resource_guard import MemoryStatus
from app.rag.exceptions import EmbeddingModelUnavailableError


def _mem(headroom_mb: float) -> MemoryStatus:
    return MemoryStatus(
        available_physical_mb=headroom_mb,
        committed_mb=27000.0 - headroom_mb,
        commit_limit_mb=27000.0,
        commit_headroom_mb=headroom_mb,
        safe_for_embedding=headroom_mb >= settings.BGE_MIN_COMMIT_HEADROOM_MB,
        threshold_mb=settings.BGE_MIN_COMMIT_HEADROOM_MB,
        source="windows_commit_charge",
    )


def _fake_worker_manager(status=WorkerStatus.READY, active_jobs=0):
    m = MagicMock()
    m.get_active_job_count.return_value = active_jobs
    m.get_status.return_value = {"status": status.value, "worker_pid": 12345, "manager_pid": 1, "last_error": None}
    return m


class TestEnsureLlmCapacity(unittest.TestCase):
    """
    Core resource-manager decision logic: whether to leave BGE alone, or
    stop it to make room for Qwen. Mocks the two collaborators
    (get_memory_status, get_worker_manager) and Ollama's /api/ps directly
    so this is fast and deterministic -- no real subprocess, no real Ollama
    server required.
    """

    def setUp(self):
        self.manager = ModelResourceManager()

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_qwen_already_resident_never_touches_bge(self, mock_mem, mock_get_wm):
        with patch.object(self.manager, "is_qwen_resident", return_value=True):
            result = self.manager.ensure_llm_capacity()
        self.assertEqual(result["resource_wait_ms"], 0.0)
        mock_get_wm.assert_not_called()  # never even looked at the worker

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_sufficient_headroom_leaves_bge_alone(self, mock_mem, mock_get_wm):
        mock_mem.return_value = _mem(settings.QWEN_MIN_COMMIT_HEADROOM_MB + 1000)
        with patch.object(self.manager, "is_qwen_resident", return_value=False):
            self.manager.ensure_llm_capacity()
        mock_get_wm.return_value.shutdown.assert_not_called()

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_insufficient_headroom_stops_bge_and_waits_for_recovery(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.READY, active_jobs=0)
        mock_get_wm.return_value = wm
        # First call (pre-stop) reports low headroom; every call after
        # shutdown() reports recovered headroom -- simulates the real
        # sequence measured in the investigation (~2.15GB -> ~5.93GB).
        low = _mem(1500)
        high = _mem(settings.QWEN_MIN_COMMIT_HEADROOM_MB + 500)
        mock_mem.side_effect = [low, low, high]

        with patch.object(self.manager, "is_qwen_resident", return_value=False):
            result = self.manager.ensure_llm_capacity()

        wm.shutdown.assert_called_once()
        self.assertGreaterEqual(result["resource_wait_ms"], 0.0)
        self.assertEqual(self.manager._state, ResourceState.NORMAL)

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_active_embedding_job_prevents_preemption(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.READY, active_jobs=1)
        mock_get_wm.return_value = wm
        mock_mem.return_value = _mem(1500)  # unsafe for Qwen

        with patch.object(self.manager, "is_qwen_resident", return_value=False):
            self.manager.ensure_llm_capacity()

        wm.shutdown.assert_not_called()

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_worker_not_resident_nothing_to_stop(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.NOT_STARTED, active_jobs=0)
        mock_get_wm.return_value = wm
        mock_mem.return_value = _mem(1500)

        with patch.object(self.manager, "is_qwen_resident", return_value=False):
            self.manager.ensure_llm_capacity()

        wm.shutdown.assert_not_called()

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_recovery_timeout_still_returns_without_raising(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.READY, active_jobs=0)
        mock_get_wm.return_value = wm
        mock_mem.return_value = _mem(1500)  # never recovers

        with patch.object(settings, "RESOURCE_RELEASE_TIMEOUT_SECONDS", 0.05), \
             patch.object(self.manager, "is_qwen_resident", return_value=False):
            result = self.manager.ensure_llm_capacity()

        wm.shutdown.assert_called_once()
        self.assertIn("resource_wait_ms", result)
        self.assertEqual(self.manager._state, ResourceState.MEMORY_PRESSURE)

    def test_never_raises_even_on_internal_failure(self):
        with patch.object(self.manager, "is_qwen_resident", side_effect=RuntimeError("boom")):
            result = self.manager.ensure_llm_capacity()
        self.assertIn("resource_wait_ms", result)  # returned cleanly, did not propagate


class TestEnsureEmbeddingAvailable(unittest.TestCase):
    @patch("app.services.model_resource_manager.get_worker_manager")
    def test_delegates_to_worker_manager_ensure_ready(self, mock_get_wm):
        wm = MagicMock()
        mock_get_wm.return_value = wm
        manager = ModelResourceManager()
        manager.ensure_embedding_available(timeout=10)
        wm.ensure_ready.assert_called_once_with(10)


class TestEnsureEmbeddingCapacity(unittest.TestCase):
    """
    The reverse (Qwen -> BGE) transition, added after a live benchmark
    proved a second consecutive DOCUMENT_RAG turn would otherwise find BGE
    permanently unable to start once Qwen was resident. Mirrors
    TestEnsureLlmCapacity's structure/mocking approach for the opposite
    direction.

    Explicitly forces EMBEDDING_PROVIDER="bge" (rather than relying on it
    being the ambient default -- it no longer is, since the E5 migration
    switched the default) because these tests exercise BGE-specific
    preemption thresholds/mechanics by design.
    """

    def setUp(self):
        self.manager = ModelResourceManager()
        self._original_provider = settings.EMBEDDING_PROVIDER
        settings.EMBEDDING_PROVIDER = "bge"

    def tearDown(self):
        settings.EMBEDDING_PROVIDER = self._original_provider

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_bge_already_ready_no_transition(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.READY, active_jobs=0)
        mock_get_wm.return_value = wm

        self.manager.ensure_embedding_capacity(timeout=10)

        wm.ensure_ready.assert_called_once_with(10)
        mock_mem.assert_not_called()  # never even checked headroom

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_sufficient_headroom_no_preemption_needed(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.NOT_STARTED, active_jobs=0)
        mock_get_wm.return_value = wm
        mock_mem.return_value = _mem(settings.BGE_MIN_COMMIT_HEADROOM_MB + 1000)

        with patch.object(self.manager, "is_qwen_resident", return_value=True), \
             patch.object(self.manager, "unload_qwen") as mock_unload:
            self.manager.ensure_embedding_capacity(timeout=10)

        wm.ensure_ready.assert_called_once_with(10)
        mock_unload.assert_not_called()

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_insufficient_headroom_and_qwen_resident_stops_qwen(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.NOT_STARTED, active_jobs=0)
        mock_get_wm.return_value = wm
        low = _mem(1500)
        high = _mem(settings.BGE_MIN_COMMIT_HEADROOM_MB + 500)
        mock_mem.side_effect = [low, low, high]

        with patch.object(self.manager, "is_qwen_resident", return_value=True), \
             patch.object(self.manager, "unload_qwen") as mock_unload:
            self.manager.ensure_embedding_capacity(timeout=10)

        mock_unload.assert_called_once()
        wm.ensure_ready.assert_called_once_with(10)
        self.assertEqual(self.manager._state, ResourceState.NORMAL)

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_insufficient_headroom_no_qwen_to_preempt(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.NOT_STARTED, active_jobs=0)
        mock_get_wm.return_value = wm
        mock_mem.return_value = _mem(1500)

        with patch.object(self.manager, "is_qwen_resident", return_value=False), \
             patch.object(self.manager, "unload_qwen") as mock_unload:
            self.manager.ensure_embedding_capacity(timeout=10)

        mock_unload.assert_not_called()
        wm.ensure_ready.assert_called_once_with(10)

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_qwen_busy_skips_preemption(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.NOT_STARTED, active_jobs=0)
        mock_get_wm.return_value = wm
        mock_mem.return_value = _mem(1500)

        self.manager._qwen_active_jobs = 1
        with patch.object(self.manager, "is_qwen_resident", return_value=True), \
             patch.object(self.manager, "unload_qwen") as mock_unload:
            self.manager.ensure_embedding_capacity(timeout=10)

        mock_unload.assert_not_called()
        wm.ensure_ready.assert_called_once_with(10)

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_recovery_timeout_still_attempts_ensure_ready(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.NOT_STARTED, active_jobs=0)
        mock_get_wm.return_value = wm
        mock_mem.return_value = _mem(1500)  # never recovers

        with patch.object(settings, "RESOURCE_RELEASE_TIMEOUT_SECONDS", 0.05), \
             patch.object(self.manager, "is_qwen_resident", return_value=True), \
             patch.object(self.manager, "unload_qwen") as mock_unload:
            self.manager.ensure_embedding_capacity(timeout=10)

        mock_unload.assert_called_once()
        wm.ensure_ready.assert_called_once_with(10)  # still attempted, not skipped
        self.assertEqual(self.manager._state, ResourceState.MEMORY_PRESSURE)

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_stale_ready_status_falls_through_to_reverse_preemption(self, mock_mem, mock_get_wm):
        """
        Regression test for a real gap found live: the cached worker status
        can say READY while the underlying process has actually died (e.g.
        reaped under memory pressure). The fast path must not just
        propagate that failure -- it must fall through to the full
        decision tree and still attempt the reverse Qwen->BGE preemption.
        """
        wm = _fake_worker_manager(status=WorkerStatus.READY, active_jobs=0)
        # First ensure_ready() call (fast path) fails despite READY status;
        # second call (after preemption) succeeds.
        wm.ensure_ready.side_effect = [
            EmbeddingModelUnavailableError("stale: worker actually not alive"),
            None,
        ]
        mock_get_wm.return_value = wm
        low = _mem(1500)
        high = _mem(settings.BGE_MIN_COMMIT_HEADROOM_MB + 500)
        mock_mem.side_effect = [low, low, high]

        with patch.object(self.manager, "is_qwen_resident", return_value=True), \
             patch.object(self.manager, "unload_qwen") as mock_unload:
            self.manager.ensure_embedding_capacity(timeout=10)

        mock_unload.assert_called_once()
        self.assertEqual(wm.ensure_ready.call_count, 2)

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_propagates_error_when_bge_still_unavailable(self, mock_mem, mock_get_wm):
        """
        Unlike ensure_llm_capacity (which never raises -- GENERAL_CHAT is
        always an acceptable fallback), ensure_embedding_capacity MUST let
        EmbeddingModelUnavailableError propagate: DOCUMENT_RAG is only ever
        selected for an explicit document request, so the caller
        (chat/service.py) needs to know grounding failed rather than
        silently proceeding as if it hadn't.
        """
        wm = _fake_worker_manager(status=WorkerStatus.NOT_STARTED, active_jobs=0)
        wm.ensure_ready.side_effect = EmbeddingModelUnavailableError("still unavailable")
        mock_get_wm.return_value = wm
        mock_mem.return_value = _mem(settings.BGE_MIN_COMMIT_HEADROOM_MB + 1000)

        with patch.object(self.manager, "is_qwen_resident", return_value=True):
            with self.assertRaises(EmbeddingModelUnavailableError):
                self.manager.ensure_embedding_capacity(timeout=10)


class TestQwenActiveJobTracking(unittest.TestCase):
    """
    Best-effort Qwen-busy hint that ensure_embedding_capacity checks before
    preempting -- prevents unloading Qwen out from under a concurrent
    request's in-flight generation (see module docstring).
    """

    def test_mark_start_and_end_round_trip(self):
        manager = ModelResourceManager()
        self.assertEqual(manager._qwen_active_jobs, 0)
        manager.mark_qwen_call_start()
        self.assertEqual(manager._qwen_active_jobs, 1)
        manager.mark_qwen_call_end()
        self.assertEqual(manager._qwen_active_jobs, 0)


class TestIsQwenResident(unittest.TestCase):
    @patch("httpx.Client")
    def test_true_when_model_present_in_api_ps(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Literal "qwen2.5:7b", matching the patched settings.MODEL_NAME
        # below -- must not depend on the real configured MODEL_NAME, which
        # is expected to change over time as SovereignX's default model does.
        mock_response.json.return_value = {"models": [{"model": "qwen2.5:7b"}]}
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        with patch.object(settings, "MODEL_NAME", "qwen2.5:7b"):
            manager = ModelResourceManager()
            self.assertTrue(manager.is_qwen_resident())

    @patch("httpx.Client")
    def test_false_when_model_absent(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        with patch.object(settings, "MODEL_NAME", "qwen2.5:7b"):
            manager = ModelResourceManager()
            self.assertFalse(manager.is_qwen_resident())

    @patch("httpx.Client")
    def test_false_on_connection_error_not_raise(self, mock_client_cls):
        mock_client_cls.return_value.__enter__.side_effect = Exception("connection refused")
        manager = ModelResourceManager()
        self.assertFalse(manager.is_qwen_resident())


class TestTransitionLockConcurrency(unittest.TestCase):
    """
    Two concurrent callers must not both decide to stop the embedding
    worker -- the transition lock serializes the decision, so the second
    caller sees the already-updated (post-stop) state and does nothing
    further. This directly tests item 13's concern (conflicting concurrent
    lifecycle operations) without needing real subprocesses.
    """

    @patch("app.services.model_resource_manager.get_worker_manager")
    @patch("app.services.model_resource_manager.get_memory_status")
    def test_concurrent_calls_stop_worker_at_most_once(self, mock_mem, mock_get_wm):
        wm = _fake_worker_manager(status=WorkerStatus.READY, active_jobs=0)

        def slow_shutdown():
            time.sleep(0.2)  # widen the race window deliberately
            wm.get_status.return_value = {
                "status": WorkerStatus.NOT_STARTED.value, "worker_pid": None,
                "manager_pid": 1, "last_error": None,
            }
        wm.shutdown.side_effect = slow_shutdown
        mock_get_wm.return_value = wm

        # Low headroom for the "before" check; recovered afterward -- shared
        # across both threads since mock_mem is a single MagicMock.
        state = {"stopped": False}

        def mem_side_effect():
            return _mem(settings.QWEN_MIN_COMMIT_HEADROOM_MB + 500) if state["stopped"] else _mem(1500)
        mock_mem.side_effect = lambda: mem_side_effect()

        orig_shutdown = wm.shutdown.side_effect

        def shutdown_and_mark():
            orig_shutdown()
            state["stopped"] = True
        wm.shutdown.side_effect = shutdown_and_mark

        manager = ModelResourceManager()
        results = []

        def worker():
            with patch.object(manager, "is_qwen_resident", return_value=False):
                results.append(manager.ensure_llm_capacity())

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertEqual(len(results), 2)
        self.assertEqual(wm.shutdown.call_count, 1)  # not stopped twice


if __name__ == "__main__":
    unittest.main()
