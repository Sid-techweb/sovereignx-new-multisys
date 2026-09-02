"""
Tests for agent_tools.execute_python()'s local/remote dispatch -- the layer
Planner calls through without ever knowing about nodes (see that module's
docstring). Distributed-mode branches are exercised with a mocked
DistributedRouter/WorkerClient so these run with no real network calls and
no Docker dependency except where a real local execution happens (guarded
the same way as test_agent_tools.py's Docker-dependent tests).
"""
import unittest
from unittest.mock import patch, MagicMock

from app.config import settings
from app.services import agent_tools
from app.services.distributed_router import RoutingDecision, CapabilityUnavailableError
from app.services.node_registry import LOCAL_NODE_ID
from app.services.worker_client import WorkerError


class TestSingleNodeModeZeroRemoteCalls(unittest.TestCase):
    """The most important invariant in this phase: distributed mode off must
    never import/construct/call anything distributed-related."""

    def test_distributed_router_never_imported_when_mode_disabled(self):
        with patch.object(settings, "SOVEREIGN_DISTRIBUTED_MODE", False):
            with patch("app.services.distributed_router.DistributedRouter.route_sandbox_execution",
                       side_effect=AssertionError("route_sandbox_execution should not be called in single-node mode")):
                with patch.object(agent_tools, "_execute_python_local", return_value={
                    "stdout": "ok", "stderr": "", "exit_code": 0, "timed_out": False, "elapsed_ms": 1.0,
                }) as mock_local:
                    result = agent_tools.execute_python("print(1)")
        mock_local.assert_called_once()
        self.assertEqual(result["execution"]["scope"], "LOCAL")
        self.assertFalse(result["execution"]["is_fallback"])
        self.assertEqual(result["metrics"]["remote_execution_ms"], 0.0)
        self.assertEqual(result["metrics"]["node_selection_ms"], 0.0)


class TestDistributedModeRemoteExecution(unittest.TestCase):
    def test_healthy_worker_executes_remotely(self):
        decision = RoutingDecision(
            scope="REMOTE", node_id="node-b", node_url="http://127.0.0.1:9001",
            execution_scope="LOCALHOST", is_fallback=False, reason="selected healthy worker node 'node-b'",
            selection_ms=1.2, health_ms=0.5,
        )
        with patch.object(settings, "SOVEREIGN_DISTRIBUTED_MODE", True):
            with patch("app.services.distributed_router.distributed_router.route_sandbox_execution", return_value=decision):
                with patch("app.services.worker_client.WorkerClient") as MockClient:
                    instance = MockClient.return_value.__enter__.return_value
                    instance.execute_code.return_value = {
                        "stdout": "remote ok\n", "stderr": "", "exit_code": 0, "timed_out": False, "elapsed_ms": 42.0,
                    }
                    result = agent_tools.execute_python("print('remote ok')")

        self.assertEqual(result["execution"]["scope"], "REMOTE")
        self.assertEqual(result["execution"]["node_id"], "node-b")
        self.assertEqual(result["execution"]["execution_scope"], "LOCALHOST")
        self.assertFalse(result["execution"]["is_fallback"])
        self.assertEqual(result["stdout"], "remote ok\n")
        self.assertEqual(result["metrics"]["sandbox_ms"], 42.0)
        self.assertGreaterEqual(result["metrics"]["remote_execution_ms"], 0.0)

    def test_no_compatible_node_raises_value_error(self):
        with patch.object(settings, "SOVEREIGN_DISTRIBUTED_MODE", True):
            with patch(
                "app.services.distributed_router.distributed_router.route_sandbox_execution",
                side_effect=CapabilityUnavailableError("No node offers SANDBOX_EXECUTION."),
            ):
                with self.assertRaises(ValueError):
                    agent_tools.execute_python("print(1)")

    def test_remote_worker_failure_falls_back_to_local_explicitly(self):
        decision = RoutingDecision(
            scope="REMOTE", node_id="node-b", node_url="http://127.0.0.1:9001",
            execution_scope="LOCALHOST", is_fallback=False, reason="selected healthy worker node 'node-b'",
            selection_ms=1.0, health_ms=0.5,
        )
        with patch.object(settings, "SOVEREIGN_DISTRIBUTED_MODE", True):
            with patch("app.services.distributed_router.distributed_router.route_sandbox_execution", return_value=decision):
                with patch("app.services.worker_client.WorkerClient") as MockClient:
                    instance = MockClient.return_value.__enter__.return_value
                    instance.execute_code.side_effect = WorkerError("connection reset mid-request")
                    with patch.object(agent_tools, "_execute_python_local", return_value={
                        "stdout": "local fallback ok", "stderr": "", "exit_code": 0, "timed_out": False, "elapsed_ms": 5.0,
                    }) as mock_local:
                        result = agent_tools.execute_python("print(1)")

        mock_local.assert_called_once()
        self.assertEqual(result["execution"]["scope"], "LOCAL")
        self.assertTrue(result["execution"]["is_fallback"], "a remote failure must be recorded as an explicit fallback, never silently presented as remote success")

    def test_router_local_fallback_decision_is_recorded_as_fallback(self):
        decision = RoutingDecision(
            scope="LOCAL", node_id=LOCAL_NODE_ID, node_url="http://localhost:11434",
            execution_scope="LOCAL", is_fallback=True, reason="no healthy remote worker available; local node supports the capability",
            selection_ms=2.0, health_ms=1.5,
        )
        with patch.object(settings, "SOVEREIGN_DISTRIBUTED_MODE", True):
            with patch("app.services.distributed_router.distributed_router.route_sandbox_execution", return_value=decision):
                with patch.object(agent_tools, "_execute_python_local", return_value={
                    "stdout": "ok", "stderr": "", "exit_code": 0, "timed_out": False, "elapsed_ms": 3.0,
                }):
                    result = agent_tools.execute_python("print(1)")

        self.assertTrue(result["execution"]["is_fallback"])
        self.assertEqual(result["execution"]["scope"], "LOCAL")


if __name__ == "__main__":
    unittest.main()
