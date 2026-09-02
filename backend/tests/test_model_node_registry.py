"""
Tests for the multi-node foundation: ModelRegistry (app/services/model_registry.py)
and NodeRegistry (app/services/node_registry.py). These are catalog/lookup
structures only -- no remote I/O is exercised here because none exists yet
(worker API/client is explicitly out of scope for this phase).
"""
import unittest
from unittest.mock import patch

from app.services.model_registry import (
    ModelRegistry,
    ModelSpec,
    ModelCapability,
    HealthState,
    model_registry as default_model_registry,
    LOCAL_NODE_ID,
)
from app.services.node_registry import (
    NodeRegistry,
    NodeSpec,
    _parse_ai_nodes_config,
    node_registry as default_node_registry,
)


class TestModelRegistryCapabilitySelection(unittest.TestCase):
    def test_find_by_capability_returns_matches_only(self):
        registry = ModelRegistry()
        registry.register(ModelSpec("chat-model", "ollama", LOCAL_NODE_ID, [ModelCapability.GENERAL_CHAT], priority=10, health=HealthState.HEALTHY))
        registry.register(ModelSpec("vision-model", "transformers", LOCAL_NODE_ID, [ModelCapability.VISION], priority=10, health=HealthState.HEALTHY))
        matches = registry.find_by_capability(ModelCapability.GENERAL_CHAT)
        self.assertEqual([m.name for m in matches], ["chat-model"])

    def test_lower_priority_number_preferred(self):
        registry = ModelRegistry()
        registry.register(ModelSpec("slow", "ollama", LOCAL_NODE_ID, [ModelCapability.CODING], priority=50, health=HealthState.HEALTHY))
        registry.register(ModelSpec("fast", "ollama", LOCAL_NODE_ID, [ModelCapability.CODING], priority=5, health=HealthState.HEALTHY))
        best = registry.best_for_capability(ModelCapability.CODING)
        self.assertEqual(best.name, "fast")

    def test_offline_models_excluded_by_default(self):
        registry = ModelRegistry()
        registry.register(ModelSpec("dead", "ollama", LOCAL_NODE_ID, [ModelCapability.REASONING], priority=1, health=HealthState.OFFLINE))
        registry.register(ModelSpec("alive", "ollama", LOCAL_NODE_ID, [ModelCapability.REASONING], priority=99, health=HealthState.HEALTHY))
        best = registry.best_for_capability(ModelCapability.REASONING)
        self.assertEqual(best.name, "alive")

    def test_no_match_returns_none(self):
        registry = ModelRegistry()
        self.assertIsNone(registry.best_for_capability(ModelCapability.SANDBOX_EXECUTION))

    def test_set_health_updates_lookup_order(self):
        registry = ModelRegistry()
        registry.register(ModelSpec("m1", "ollama", LOCAL_NODE_ID, [ModelCapability.GENERAL_CHAT], priority=10, health=HealthState.HEALTHY))
        registry.set_health("m1", HealthState.OFFLINE)
        self.assertIsNone(registry.best_for_capability(ModelCapability.GENERAL_CHAT))


class TestDefaultModelRegistrySeeding(unittest.TestCase):
    """The module-level singleton, built from actual current app.config.settings."""

    def test_seeded_with_current_chat_model_and_embedding_and_vision(self):
        from app.config import settings
        names = {m.name for m in default_model_registry.list_models()}
        if settings.MODEL_PROVIDER.lower() == "ollama" and settings.MODEL_NAME:
            self.assertIn(settings.MODEL_NAME, names)
        self.assertIn(settings.EMBEDDING_MODEL, names)
        self.assertIn("Qwen/Qwen2-VL-2B-Instruct", names)

    def test_sandbox_execution_capability_is_registered(self):
        matches = default_model_registry.find_by_capability(ModelCapability.SANDBOX_EXECUTION, exclude_unhealthy=False)
        self.assertTrue(any(m.name == "docker-python-sandbox" for m in matches))

    def test_vision_and_ocr_both_map_to_qwen2_vl(self):
        vision_matches = default_model_registry.find_by_capability(ModelCapability.VISION, exclude_unhealthy=False)
        ocr_matches = default_model_registry.find_by_capability(ModelCapability.OCR, exclude_unhealthy=False)
        self.assertTrue(any(m.name == "Qwen/Qwen2-VL-2B-Instruct" for m in vision_matches))
        self.assertTrue(any(m.name == "Qwen/Qwen2-VL-2B-Instruct" for m in ocr_matches))


class TestNodeRegistrySingleNodeDefault(unittest.TestCase):
    def test_default_registry_is_single_node_when_not_distributed(self):
        from app.config import settings
        if settings.SOVEREIGN_DISTRIBUTED_MODE:
            self.skipTest("SOVEREIGN_DISTRIBUTED_MODE is on in this environment")
        self.assertEqual(len(default_node_registry.list_nodes()), 1)
        self.assertFalse(default_node_registry.is_distributed())
        local = default_node_registry.get(LOCAL_NODE_ID)
        self.assertIsNotNone(local)
        self.assertEqual(local.role, "primary")

    def test_no_hardcoded_ip_in_default_local_node_url(self):
        """The local node's URL must come from configuration
        (OLLAMA_BASE_URL), never a literal private IP baked into this
        module -- mirrors the same rule already enforced in sovereignty.py."""
        local = default_node_registry.get(LOCAL_NODE_ID)
        self.assertIn(local.url, ("http://localhost:11434",) if local.url.startswith("http://localhost") else (local.url,))
        self.assertNotRegex(local.url, r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        self.assertNotRegex(local.url, r"\b192\.168\.\d{1,3}\.\d{1,3}\b")


class TestAiNodesConfigParsing(unittest.TestCase):
    def test_empty_config_yields_no_nodes(self):
        self.assertEqual(_parse_ai_nodes_config(""), [])

    def test_valid_config_parsed_into_node_specs(self):
        raw = '[{"node_id": "worker-1", "url": "http://192.168.1.50:8000", "role": "worker", "models": ["qwen2.5:7b"], "capabilities": ["GENERAL_CHAT"]}]'
        nodes = _parse_ai_nodes_config(raw)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].node_id, "worker-1")
        self.assertEqual(nodes[0].capabilities, [ModelCapability.GENERAL_CHAT])

    def test_malformed_json_yields_no_nodes_not_an_exception(self):
        self.assertEqual(_parse_ai_nodes_config("{not valid json"), [])

    def test_non_array_json_yields_no_nodes(self):
        self.assertEqual(_parse_ai_nodes_config('{"node_id": "x"}'), [])

    def test_entry_missing_required_field_is_skipped_not_fatal(self):
        raw = '[{"node_id": "incomplete"}, {"node_id": "ok", "url": "http://example-worker:8000"}]'
        nodes = _parse_ai_nodes_config(raw)
        self.assertEqual([n.node_id for n in nodes], ["ok"])


class TestDistributedModeGating(unittest.TestCase):
    """When SOVEREIGN_DISTRIBUTED_MODE is False, building the registry must
    never touch AI_NODES_CONFIG at all -- proven by patching the parser to
    raise if it's called."""

    def test_ai_nodes_config_never_parsed_when_distributed_mode_off(self):
        from app.services import node_registry as node_registry_module

        with patch.object(node_registry_module, "_parse_ai_nodes_config", side_effect=AssertionError("should not be called")):
            with patch("app.config.settings.SOVEREIGN_DISTRIBUTED_MODE", False), \
                 patch("app.config.settings.AI_NODES_CONFIG", '[{"node_id": "should-not-be-parsed", "url": "http://x"}]'):
                registry = node_registry_module._build_default_registry()
                self.assertEqual(len(registry.list_nodes()), 1)

    def test_ai_nodes_config_parsed_when_distributed_mode_on(self):
        from app.services import node_registry as node_registry_module

        with patch("app.config.settings.SOVEREIGN_DISTRIBUTED_MODE", True), \
             patch("app.config.settings.AI_NODES_CONFIG", '[{"node_id": "worker-2", "url": "http://example-worker:8000", "capabilities": ["CODING"]}]'):
            registry = node_registry_module._build_default_registry()
            node_ids = {n.node_id for n in registry.list_nodes()}
            self.assertIn("worker-2", node_ids)
            self.assertTrue(registry.is_distributed())


if __name__ == "__main__":
    unittest.main()
