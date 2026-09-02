"""
Lightweight local model registry -- the project statement's "multiple
open-weight models... automatic selection based on task requirements".

Deliberately small: a list of ModelSpec entries with declared capabilities,
and a capability -> best-match selector. This is NOT a general-purpose
model-serving framework -- it exists so a task's required capability
(general_chat, rag_generation, coding, vision, embedding) maps to a model
declaratively instead of being decided by scattered if/else statements
across chat/service.py, agents.py, and the extractors.

Today every capability still resolves to the one model that already
provides it (qwen3.5:4b for text, Qwen2-VL-2B-Instruct for vision,
multilingual-e5-small/BGE-M3 for embedding) -- registering them here does
not change runtime behavior yet, it makes the mapping explicit and gives
node-aware routing (see node_registry.py) a single place to extend when a
second model or a second node is added, instead of a rewrite.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from app.config import settings

logger = logging.getLogger("sovereignx")


class Capability(str, Enum):
    GENERAL_CHAT = "general_chat"
    RAG_GENERATION = "rag_generation"
    CODING = "coding"
    VISION = "vision"
    EMBEDDING = "embedding"


class ModelHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


@dataclass
class ModelSpec:
    name: str
    provider: str  # "ollama" | "transformers" | "sentence-transformers"
    node_id: str  # which node (see node_registry.py) actually runs this model
    capabilities: List[Capability]
    context_length: Optional[int] = None
    multimodal: bool = False
    priority: int = 100  # lower = preferred when multiple specs share a capability
    estimated_memory_mb: Optional[int] = None
    health: ModelHealth = ModelHealth.UNKNOWN


def _default_registry() -> List[ModelSpec]:
    """
    Reflects the models this backend actually has wired up today. A second
    node's models are added by node_registry.py at runtime when
    SOVEREIGN_DISTRIBUTED_MODE is enabled -- see get_model_registry().
    """
    embedding_model = ModelSpec(
        name=settings.E5_EMBEDDING_MODEL if settings.EMBEDDING_PROVIDER == "e5" else settings.EMBEDDING_MODEL,
        provider="sentence-transformers",
        node_id="local",
        capabilities=[Capability.EMBEDDING],
        estimated_memory_mb=400 if settings.EMBEDDING_PROVIDER == "e5" else 1900,
        priority=10,
    )
    return [
        ModelSpec(
            name=settings.MODEL_NAME or "qwen3.5:4b",
            provider="ollama",
            node_id="local",
            capabilities=[Capability.GENERAL_CHAT, Capability.RAG_GENERATION, Capability.CODING],
            context_length=4096,
            estimated_memory_mb=3100,
            priority=10,
        ),
        ModelSpec(
            name="Qwen/Qwen2-VL-2B-Instruct",
            provider="transformers",
            node_id="local",
            capabilities=[Capability.VISION],
            multimodal=True,
            estimated_memory_mb=2500,
            priority=10,
        ),
        embedding_model,
    ]


class ModelRegistry:
    """
    Process-wide registry: TaskClassifier/chat routing decides a
    Capability is needed; ModelSelector picks the best available ModelSpec
    for it; NodeSelector (node_registry.py) resolves that spec's node_id to
    an actual endpoint. Registration is additive -- distributed mode adds
    remote-node specs without removing the local ones, so single-node
    operation always keeps working even if a remote node's specs are also
    registered.
    """
    def __init__(self):
        self._specs: List[ModelSpec] = []

    def register(self, spec: ModelSpec) -> None:
        self._specs = [s for s in self._specs if not (s.name == spec.name and s.node_id == spec.node_id)]
        self._specs.append(spec)

    def register_many(self, specs: List[ModelSpec]) -> None:
        for s in specs:
            self.register(s)

    def all_specs(self) -> List[ModelSpec]:
        return list(self._specs)

    def select(self, capability: Capability, exclude_offline: bool = True) -> Optional[ModelSpec]:
        """
        Capability-based selection, NOT round-robin: returns the
        lowest-priority-number (most preferred), non-OFFLINE spec that
        declares this capability. Ties broken by registration order.
        """
        candidates = [s for s in self._specs if capability in s.capabilities]
        if exclude_offline:
            candidates = [s for s in candidates if s.health != ModelHealth.OFFLINE]
        if not candidates:
            return None
        return min(candidates, key=lambda s: s.priority)

    def select_all_capable(self, capability: Capability, exclude_offline: bool = True) -> List[ModelSpec]:
        candidates = [s for s in self._specs if capability in s.capabilities]
        if exclude_offline:
            candidates = [s for s in candidates if s.health != ModelHealth.OFFLINE]
        return sorted(candidates, key=lambda s: s.priority)

    def update_health(self, name: str, node_id: str, health: ModelHealth) -> None:
        for s in self._specs:
            if s.name == name and s.node_id == node_id:
                s.health = health
                return


_registry_lock_instance: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    global _registry_lock_instance
    if _registry_lock_instance is None:
        _registry_lock_instance = ModelRegistry()
        _registry_lock_instance.register_many(_default_registry())
    return _registry_lock_instance


def reset_model_registry_for_testing() -> None:
    global _registry_lock_instance
    _registry_lock_instance = None
