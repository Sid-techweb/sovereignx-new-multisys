"""
Model registry -- a central, queryable catalog of which models exist, what
they can do, and where they run. This is the foundation multi-node routing
will eventually select against (see app/services/node_registry.py); by
itself it changes no runtime behavior -- nothing yet consults it to pick a
model instead of the existing hardcoded settings.MODEL_NAME/EMBEDDING_MODEL
wiring.

Deliberately NOT specific to any one model family (not "E5", not
"qwen3.5") -- ModelSpec/ModelCapability describe any model this app could
plug in, and the registry is seeded from the actual current
configuration/deployment, not a hardcoded assumption about which model is
"the" model.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("sovereignx")


class ModelCapability(str, Enum):
    """What a model can be asked to do -- the axis capability-based routing
    selects on, instead of a round-robin or a single hardcoded model name."""
    GENERAL_CHAT = "GENERAL_CHAT"
    RAG_GENERATION = "RAG_GENERATION"
    VISION = "VISION"
    CODING = "CODING"
    REASONING = "REASONING"
    OCR = "OCR"
    REPORT_GENERATION = "REPORT_GENERATION"
    SANDBOX_EXECUTION = "SANDBOX_EXECUTION"


class HealthState(str, Enum):
    """Shared by ModelSpec and NodeSpec (see node_registry.py) -- a model's
    and a node's health are reported the same way for one consistent
    routing/health-check vocabulary."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


@dataclass
class ModelSpec:
    name: str
    provider: str  # "ollama" | "mock" | "transformers" (in-process, e.g. Qwen2-VL/BGE-M3)
    node_id: str
    capabilities: List[ModelCapability]
    priority: int = 100  # lower = preferred when multiple models share a capability
    health: HealthState = HealthState.UNKNOWN
    estimated_memory_mb: int = 0


class ModelRegistry:
    """
    In-memory catalog, not a live process supervisor -- health is a field
    callers can update (e.g. from ModelResourceManager or a future node
    health-check loop), not something this class polls on its own.
    """

    def __init__(self):
        self._models: Dict[str, ModelSpec] = {}

    def register(self, spec: ModelSpec) -> None:
        self._models[spec.name] = spec
        logger.info(
            f"model_registry: registered '{spec.name}' provider={spec.provider} "
            f"node={spec.node_id} capabilities={[c.value for c in spec.capabilities]}"
        )

    def get(self, name: str) -> Optional[ModelSpec]:
        return self._models.get(name)

    def list_models(self) -> List[ModelSpec]:
        return list(self._models.values())

    def set_health(self, name: str, health: HealthState) -> None:
        if name in self._models:
            self._models[name].health = health

    def find_by_capability(
        self,
        capability: ModelCapability,
        exclude_unhealthy: bool = True,
    ) -> List[ModelSpec]:
        """
        Models offering `capability`, best (lowest priority number, then
        healthiest) first. This is the seam future distributed routing calls
        instead of anything hardcoding a model name.
        """
        candidates = [m for m in self._models.values() if capability in m.capabilities]
        if exclude_unhealthy:
            candidates = [m for m in candidates if m.health != HealthState.OFFLINE]
        return sorted(candidates, key=lambda m: (m.priority, m.health != HealthState.HEALTHY))

    def best_for_capability(
        self,
        capability: ModelCapability,
        exclude_unhealthy: bool = True,
    ) -> Optional[ModelSpec]:
        matches = self.find_by_capability(capability, exclude_unhealthy=exclude_unhealthy)
        return matches[0] if matches else None


LOCAL_NODE_ID = "local"


def _build_default_registry() -> ModelRegistry:
    """
    Seeds the registry from this deployment's actual current configuration
    (app.config.settings) -- not a switch to a different model, just naming
    what is already running today so capability-based lookup has something
    real to query. All models are attached to node_id=LOCAL_NODE_ID; single-
    node stays the default (see node_registry.py) until distributed mode is
    turned on.
    """
    from app.config import settings

    registry = ModelRegistry()

    if settings.MODEL_PROVIDER.lower() == "ollama" and settings.MODEL_NAME:
        registry.register(ModelSpec(
            name=settings.MODEL_NAME,
            provider="ollama",
            node_id=LOCAL_NODE_ID,
            capabilities=[ModelCapability.GENERAL_CHAT, ModelCapability.RAG_GENERATION, ModelCapability.CODING, ModelCapability.REASONING],
            priority=10,
            health=HealthState.UNKNOWN,
            estimated_memory_mb=4096,
        ))
    else:
        registry.register(ModelSpec(
            name="mock-model",
            provider="mock",
            node_id=LOCAL_NODE_ID,
            capabilities=[ModelCapability.GENERAL_CHAT, ModelCapability.RAG_GENERATION, ModelCapability.CODING, ModelCapability.REASONING],
            priority=10,
            health=HealthState.HEALTHY,
            estimated_memory_mb=0,
        ))

    # BGE-M3 -- the embedding model that powers retrieval, run in its own
    # isolated process (embedding_worker_manager.py), not through the chat
    # ModelGateway. Registered here as a capability provider regardless.
    registry.register(ModelSpec(
        name=settings.EMBEDDING_MODEL,
        provider="transformers",
        node_id=LOCAL_NODE_ID,
        capabilities=[ModelCapability.RAG_GENERATION],
        priority=10,
        health=HealthState.UNKNOWN,
        estimated_memory_mb=1900,
    ))

    # Qwen2-VL -- in-process transformers vision/OCR model used by the
    # document-intake extraction pipeline (app/services/extractors.py).
    registry.register(ModelSpec(
        name="Qwen/Qwen2-VL-2B-Instruct",
        provider="transformers",
        node_id=LOCAL_NODE_ID,
        capabilities=[ModelCapability.VISION, ModelCapability.OCR],
        priority=10,
        health=HealthState.UNKNOWN,
        estimated_memory_mb=6000,
    ))

    # Report generation is currently served by the same chat model, not a
    # separate one -- expressed here as an additional capability on it
    # rather than inventing a model that doesn't exist.
    primary = registry.get(settings.MODEL_NAME) if settings.MODEL_PROVIDER.lower() == "ollama" else registry.get("mock-model")
    if primary and ModelCapability.REPORT_GENERATION not in primary.capabilities:
        primary.capabilities.append(ModelCapability.REPORT_GENERATION)

    # execute_python's sandbox (app/services/sandbox.py) is infrastructure,
    # not a model -- but it's still a "capability that can be requested",
    # represented as a nameless-model-free entry so capability lookup has
    # one consistent interface for it too.
    registry.register(ModelSpec(
        name="docker-python-sandbox",
        provider="sandbox",
        node_id=LOCAL_NODE_ID,
        capabilities=[ModelCapability.SANDBOX_EXECUTION],
        priority=10,
        health=HealthState.UNKNOWN,
        estimated_memory_mb=256,
    ))

    return registry


# Singleton instance, following the same module-level-singleton convention
# already used by app.services.tools.tool_registry.
model_registry = _build_default_registry()
