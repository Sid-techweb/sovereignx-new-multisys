"""
Tests for the "2 lap sov" foundation: model registry (capability-based
selection), node registry (config-driven, single-node fallback, trust
classification), and the distributed router (failover, never a silent
wrong-capability substitution).

No second physical machine is required for these to be meaningful: remote
nodes are exercised via a mocked worker HTTP call and an httpx mock
transport for health checks -- what's under test is SovereignX's own
routing/failover/trust logic, not a live network round-trip (that is
explicitly called out as pending live validation in the migration report).
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.services.model_registry import (
    Capability, ModelSpec, ModelHealth, ModelRegistry,
    get_model_registry, reset_model_registry_for_testing,
)
from app.services.node_registry import (
    LOCAL_NODE_ID, NodeSpec, NodeHealth, NodeRegistry, NetworkTarget,
    classify_network_target, get_node_registry, reset_node_registry_for_testing,
)


def _run(coro):
    # asyncio.run() creates and cleanly closes a fresh event loop per call --
    # asyncio.get_event_loop() was flaky when this suite runs alongside
    # pytest-asyncio-managed tests elsewhere (a stale/closed loop from
    # another test file could be picked up), caught via a full-suite run.
    return asyncio.run(coro)


class TestModelRegistry(unittest.TestCase):
    def setUp(self):
        reset_model_registry_for_testing()

    def tearDown(self):
        reset_model_registry_for_testing()

    def test_default_registry_covers_general_chat_and_vision(self):
        registry = get_model_registry()
        general = registry.select(Capability.GENERAL_CHAT)
        vision = registry.select(Capability.VISION)
        self.assertIsNotNone(general)
        self.assertIsNotNone(vision)
        self.assertNotEqual(general.name, vision.name)

    def test_selection_is_capability_based_not_first_registered(self):
        registry = ModelRegistry()
        low_priority = ModelSpec(name="model-a", provider="ollama", node_id="local",
                                  capabilities=[Capability.CODING], priority=50)
        high_priority = ModelSpec(name="model-b", provider="ollama", node_id="local",
                                   capabilities=[Capability.CODING], priority=5)
        registry.register(low_priority)
        registry.register(high_priority)
        selected = registry.select(Capability.CODING)
        self.assertEqual(selected.name, "model-b")  # lower priority number wins

    def test_offline_model_excluded_from_selection(self):
        registry = ModelRegistry()
        spec = ModelSpec(name="only-model", provider="ollama", node_id="local",
                          capabilities=[Capability.CODING], health=ModelHealth.OFFLINE)
        registry.register(spec)
        self.assertIsNone(registry.select(Capability.CODING))
        # Still selectable if the caller explicitly wants offline candidates too.
        self.assertIsNotNone(registry.select(Capability.CODING, exclude_offline=False))

    def test_no_model_for_unregistered_capability_returns_none(self):
        registry = ModelRegistry()
        self.assertIsNone(registry.select(Capability.CODING))

    def test_update_health_affects_future_selection(self):
        registry = ModelRegistry()
        spec = ModelSpec(name="flaky-model", provider="ollama", node_id="local", capabilities=[Capability.CODING])
        registry.register(spec)
        self.assertIsNotNone(registry.select(Capability.CODING))
        registry.update_health("flaky-model", "local", ModelHealth.OFFLINE)
        self.assertIsNone(registry.select(Capability.CODING))


class TestNodeRegistrySingleNodeFallback(unittest.TestCase):
    def setUp(self):
        self._original_mode = settings.SOVEREIGN_DISTRIBUTED_MODE
        self._original_config = settings.AI_NODES_CONFIG
        settings.SOVEREIGN_DISTRIBUTED_MODE = False
        settings.AI_NODES_CONFIG = ""
        reset_node_registry_for_testing()

    def tearDown(self):
        settings.SOVEREIGN_DISTRIBUTED_MODE = self._original_mode
        settings.AI_NODES_CONFIG = self._original_config
        reset_node_registry_for_testing()

    def test_distributed_mode_false_yields_only_local_node(self):
        registry = get_node_registry()
        nodes = registry.list_nodes()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].node_id, LOCAL_NODE_ID)

    def test_local_node_is_always_healthy(self):
        registry = get_node_registry()
        self.assertEqual(registry.check_health(LOCAL_NODE_ID), NodeHealth.HEALTHY)

    def test_ai_nodes_config_ignored_when_distributed_mode_off(self):
        settings.AI_NODES_CONFIG = '[{"node_id": "node_b", "url": "http://192.168.1.50:8100", "role": "secondary"}]'
        reset_node_registry_for_testing()
        registry = get_node_registry()
        self.assertIsNone(registry.get("node_b"))
        self.assertEqual(len(registry.list_nodes()), 1)


class TestNodeRegistryDistributedMode(unittest.TestCase):
    def setUp(self):
        self._original_mode = settings.SOVEREIGN_DISTRIBUTED_MODE
        self._original_config = settings.AI_NODES_CONFIG
        settings.SOVEREIGN_DISTRIBUTED_MODE = True
        settings.AI_NODES_CONFIG = (
            '[{"node_id": "node_b", "url": "http://192.168.1.50:8100", '
            '"role": "secondary", "models": ["qwen3.5:4b"]}]'
        )
        reset_node_registry_for_testing()

    def tearDown(self):
        settings.SOVEREIGN_DISTRIBUTED_MODE = self._original_mode
        settings.AI_NODES_CONFIG = self._original_config
        reset_node_registry_for_testing()

    def test_local_node_always_present_alongside_configured_remote(self):
        registry = get_node_registry()
        node_ids = {n.node_id for n in registry.list_nodes()}
        self.assertEqual(node_ids, {LOCAL_NODE_ID, "node_b"})

    def test_no_hardcoded_ip_is_used_the_configured_one_is(self):
        registry = get_node_registry()
        node = registry.get("node_b")
        self.assertEqual(node.url, "http://192.168.1.50:8100")

    def test_malformed_json_config_yields_zero_remote_nodes_not_a_crash(self):
        settings.AI_NODES_CONFIG = "{not valid json"
        reset_node_registry_for_testing()
        registry = get_node_registry()
        self.assertEqual(registry.remote_nodes(), [])

    def test_trusted_hosts_includes_configured_node_host(self):
        registry = get_node_registry()
        self.assertIn("192.168.1.50", registry.trusted_hosts())


class TestNetworkTargetClassification(unittest.TestCase):
    def setUp(self):
        self._original_mode = settings.SOVEREIGN_DISTRIBUTED_MODE
        self._original_config = settings.AI_NODES_CONFIG
        settings.SOVEREIGN_DISTRIBUTED_MODE = True
        settings.AI_NODES_CONFIG = '[{"node_id": "node_b", "url": "http://192.168.1.50:8100", "role": "secondary"}]'
        reset_node_registry_for_testing()

    def tearDown(self):
        settings.SOVEREIGN_DISTRIBUTED_MODE = self._original_mode
        settings.AI_NODES_CONFIG = self._original_config
        reset_node_registry_for_testing()

    def test_localhost_is_localhost(self):
        self.assertEqual(classify_network_target("http://127.0.0.1:8000/health"), NetworkTarget.LOCALHOST)
        self.assertEqual(classify_network_target("localhost"), NetworkTarget.LOCALHOST)

    def test_configured_node_is_private_lan(self):
        self.assertEqual(classify_network_target("http://192.168.1.50:8100/worker/chat"), NetworkTarget.PRIVATE_LAN)

    def test_unconfigured_private_ip_is_not_auto_trusted(self):
        """Explicit project requirement: an RFC1918 address is NOT
        automatically PRIVATE_LAN just because it looks internal -- only a
        configured, approved node is."""
        self.assertEqual(classify_network_target("http://192.168.1.99:9999"), NetworkTarget.EXTERNAL)

    def test_public_url_is_external(self):
        self.assertEqual(classify_network_target("https://api.openai.com/v1/chat"), NetworkTarget.EXTERNAL)


class TestDistributedRouterFailover(unittest.TestCase):
    def setUp(self):
        reset_model_registry_for_testing()
        self._original_mode = settings.SOVEREIGN_DISTRIBUTED_MODE
        self._original_config = settings.AI_NODES_CONFIG
        settings.SOVEREIGN_DISTRIBUTED_MODE = True
        settings.AI_NODES_CONFIG = '[{"node_id": "node_b", "url": "http://192.168.1.50:8100", "role": "secondary"}]'
        reset_node_registry_for_testing()

    def tearDown(self):
        reset_model_registry_for_testing()
        settings.SOVEREIGN_DISTRIBUTED_MODE = self._original_mode
        settings.AI_NODES_CONFIG = self._original_config
        reset_node_registry_for_testing()

    def test_no_candidate_raises_capability_unavailable(self):
        from app.services.distributed_router import route_capability_request, CapabilityUnavailableError
        from app.services.model_registry import get_model_registry as gmr
        # Fresh empty registry -- nothing declares CODING.
        registry = gmr()
        registry._specs = []  # deliberately empty for this test
        with self.assertRaises(CapabilityUnavailableError):
            _run(route_capability_request(Capability.CODING, [{"role": "user", "content": "hi"}]))

    def test_remote_node_offline_fails_over_to_local(self):
        from app.services.distributed_router import route_capability_request
        from app.services.model_registry import get_model_registry as gmr, ModelSpec as MS

        registry = gmr()
        registry._specs = [
            MS(name="remote-model", provider="ollama", node_id="node_b", capabilities=[Capability.CODING], priority=1),
            MS(name="local-model", provider="ollama", node_id=LOCAL_NODE_ID, capabilities=[Capability.CODING], priority=50),
        ]

        with patch("app.services.distributed_router.get_node_registry") as mock_get_nr:
            mock_nr = NodeRegistry.__new__(NodeRegistry)
            mock_nr._nodes = {
                LOCAL_NODE_ID: NodeSpec(node_id=LOCAL_NODE_ID, url="", role="primary", health=NodeHealth.HEALTHY),
                "node_b": NodeSpec(node_id="node_b", url="http://192.168.1.50:8100", role="secondary", health=NodeHealth.OFFLINE),
            }
            mock_nr.check_health = lambda node_id, timeout=3.0: NodeHealth.OFFLINE if node_id == "node_b" else NodeHealth.HEALTHY
            mock_nr.get = lambda node_id: mock_nr._nodes.get(node_id)
            mock_get_nr.return_value = mock_nr

            with patch("app.services.distributed_router.get_gateway") as mock_get_gw:
                mock_gateway = AsyncMock()
                mock_gateway.chat_completion = AsyncMock(return_value="local answer")
                mock_get_gw.return_value = mock_gateway

                result = _run(route_capability_request(Capability.CODING, [{"role": "user", "content": "hi"}]))

        self.assertEqual(result["node_id"], LOCAL_NODE_ID)
        self.assertEqual(result["content"], "local answer")

    def test_remote_worker_call_timeout_is_not_a_crash_and_fails_over(self):
        from app.services.distributed_router import route_capability_request
        from app.services.model_registry import get_model_registry as gmr, ModelSpec as MS
        from app.services.worker_client import WorkerCallError

        registry = gmr()
        registry._specs = [
            MS(name="remote-model", provider="ollama", node_id="node_b", capabilities=[Capability.CODING], priority=1),
            MS(name="local-model", provider="ollama", node_id=LOCAL_NODE_ID, capabilities=[Capability.CODING], priority=50),
        ]

        with patch("app.services.distributed_router.get_node_registry") as mock_get_nr:
            mock_nr = NodeRegistry.__new__(NodeRegistry)
            mock_nr._nodes = {
                LOCAL_NODE_ID: NodeSpec(node_id=LOCAL_NODE_ID, url="", role="primary", health=NodeHealth.HEALTHY),
                "node_b": NodeSpec(node_id="node_b", url="http://192.168.1.50:8100", role="secondary", health=NodeHealth.HEALTHY),
            }
            mock_nr.check_health = lambda node_id, timeout=3.0: NodeHealth.HEALTHY
            mock_nr.get = lambda node_id: mock_nr._nodes.get(node_id)
            mock_get_nr.return_value = mock_nr

            with patch(
                "app.services.distributed_router.call_remote_worker_chat",
                new=AsyncMock(side_effect=WorkerCallError("node_b timed out after 60s")),
            ):
                with patch("app.services.distributed_router.get_gateway") as mock_get_gw:
                    mock_gateway = AsyncMock()
                    mock_gateway.chat_completion = AsyncMock(return_value="local fallback answer")
                    mock_get_gw.return_value = mock_gateway

                    result = _run(route_capability_request(Capability.CODING, [{"role": "user", "content": "hi"}]))

        self.assertEqual(result["node_id"], LOCAL_NODE_ID)
        self.assertEqual(result["content"], "local fallback answer")


class TestWorkerAPIAuth(unittest.TestCase):
    def setUp(self):
        self._original_secret = settings.NODE_SHARED_SECRET
        settings.NODE_SHARED_SECRET = "test-shared-secret"

    def tearDown(self):
        settings.NODE_SHARED_SECRET = self._original_secret

    def test_health_endpoint_requires_no_auth(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/worker/health")
        self.assertEqual(resp.status_code, 200)

    def test_chat_endpoint_rejects_missing_token(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.post("/worker/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(resp.status_code, 401)

    def test_chat_endpoint_rejects_wrong_token(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.post(
            "/worker/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Node-Token": "wrong-secret"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_unconfigured_secret_refuses_everything(self):
        from fastapi.testclient import TestClient
        from app.main import app
        settings.NODE_SHARED_SECRET = ""
        client = TestClient(app)
        resp = client.post(
            "/worker/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Node-Token": "anything"},
        )
        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
