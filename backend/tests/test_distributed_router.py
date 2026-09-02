"""
Tests for DistributedRouter (app/services/distributed_router.py) and the
node health cache (app/services/node_health_cache.py) in isolation --
constructed with injected NodeRegistry/NodeHealthCache instances so these
never touch the real module-level singletons or make a real network call;
health probes are exercised by patching WorkerClient at its home module.
"""
import unittest
from unittest.mock import patch, MagicMock

from app.services.distributed_router import DistributedRouter, CapabilityUnavailableError
from app.services.model_registry import HealthState, ModelCapability
from app.services.node_health_cache import NodeHealthCache
from app.services.node_registry import LOCAL_NODE_ID, NodeRegistry, NodeSpec
from app.services.worker_client import WorkerHealth, WorkerUnavailableError


def _local_only_registry(local_has_sandbox: bool = True) -> NodeRegistry:
    reg = NodeRegistry()
    caps = [ModelCapability.SANDBOX_EXECUTION] if local_has_sandbox else []
    reg.register(NodeSpec(node_id=LOCAL_NODE_ID, url="http://localhost:11434", role="primary", capabilities=caps))
    return reg


def _registry_with_worker(worker_url="http://127.0.0.1:9001", local_has_sandbox=True) -> NodeRegistry:
    reg = _local_only_registry(local_has_sandbox)
    reg.register(NodeSpec(
        node_id="node-b", url=worker_url, role="worker",
        capabilities=[ModelCapability.SANDBOX_EXECUTION], health=HealthState.UNKNOWN,
    ))
    return reg


class TestNodeHealthCache(unittest.TestCase):
    def test_miss_returns_none(self):
        cache = NodeHealthCache(ttl_seconds=10.0)
        self.assertIsNone(cache.get("node-b"))

    def test_set_then_get_within_ttl(self):
        cache = NodeHealthCache(ttl_seconds=10.0)
        cache.set("node-b", HealthState.HEALTHY)
        self.assertEqual(cache.get("node-b"), HealthState.HEALTHY)

    def test_expired_entry_returns_none(self):
        cache = NodeHealthCache(ttl_seconds=0.01)
        cache.set("node-b", HealthState.HEALTHY)
        import time
        time.sleep(0.05)
        self.assertIsNone(cache.get("node-b"))

    def test_invalidate_forces_miss(self):
        cache = NodeHealthCache(ttl_seconds=10.0)
        cache.set("node-b", HealthState.HEALTHY)
        cache.invalidate("node-b")
        self.assertIsNone(cache.get("node-b"))


class TestDistributedRouterSelection(unittest.TestCase):
    def test_no_remote_node_configured_falls_back_to_local(self):
        registry = _local_only_registry(local_has_sandbox=True)
        router = DistributedRouter(registry=registry, health_cache=NodeHealthCache(ttl_seconds=10.0))
        decision = router.route_sandbox_execution()
        self.assertEqual(decision.scope, "LOCAL")
        self.assertTrue(decision.is_fallback)
        self.assertEqual(decision.execution_scope, "LOCAL")

    def test_no_node_at_all_supports_capability_raises(self):
        registry = _local_only_registry(local_has_sandbox=False)
        router = DistributedRouter(registry=registry, health_cache=NodeHealthCache(ttl_seconds=10.0))
        with self.assertRaises(CapabilityUnavailableError):
            router.route_sandbox_execution()

    def test_healthy_remote_worker_selected(self):
        registry = _registry_with_worker()
        with patch("app.services.distributed_router.WorkerClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.health.return_value = WorkerHealth(node_id="node-b", status="healthy", role="worker", ready=True)
            router = DistributedRouter(registry=registry, health_cache=NodeHealthCache(ttl_seconds=10.0))
            decision = router.route_sandbox_execution()
        self.assertEqual(decision.scope, "REMOTE")
        self.assertEqual(decision.node_id, "node-b")
        self.assertFalse(decision.is_fallback)
        self.assertEqual(decision.execution_scope, "LOCALHOST")

    def test_offline_remote_worker_falls_back_to_local(self):
        registry = _registry_with_worker()
        with patch("app.services.distributed_router.WorkerClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.health.side_effect = WorkerUnavailableError("connection refused")
            router = DistributedRouter(registry=registry, health_cache=NodeHealthCache(ttl_seconds=10.0))
            decision = router.route_sandbox_execution()
        self.assertEqual(decision.scope, "LOCAL")
        self.assertTrue(decision.is_fallback)

    def test_offline_worker_with_no_local_capability_raises(self):
        registry = _registry_with_worker(local_has_sandbox=False)
        with patch("app.services.distributed_router.WorkerClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.health.side_effect = WorkerUnavailableError("connection refused")
            router = DistributedRouter(registry=registry, health_cache=NodeHealthCache(ttl_seconds=10.0))
            with self.assertRaises(CapabilityUnavailableError):
                router.route_sandbox_execution()


class TestDistributedRouterHealthCacheReuse(unittest.TestCase):
    def test_second_routing_decision_within_ttl_does_not_reprobe(self):
        registry = _registry_with_worker()
        health_cache = NodeHealthCache(ttl_seconds=30.0)
        with patch("app.services.distributed_router.WorkerClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.health.return_value = WorkerHealth(node_id="node-b", status="healthy", role="worker", ready=True)
            router = DistributedRouter(registry=registry, health_cache=health_cache)
            router.route_sandbox_execution()
            router.route_sandbox_execution()
        self.assertEqual(MockClient.call_count, 1, "second routing decision should reuse cached health, not re-probe")

    def test_expired_cache_triggers_reprobe(self):
        registry = _registry_with_worker()
        health_cache = NodeHealthCache(ttl_seconds=0.01)
        with patch("app.services.distributed_router.WorkerClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.health.return_value = WorkerHealth(node_id="node-b", status="healthy", role="worker", ready=True)
            router = DistributedRouter(registry=registry, health_cache=health_cache)
            router.route_sandbox_execution()
            import time
            time.sleep(0.05)
            router.route_sandbox_execution()
        self.assertEqual(MockClient.call_count, 2, "expired cache entry should trigger a fresh probe")


if __name__ == "__main__":
    unittest.main()
