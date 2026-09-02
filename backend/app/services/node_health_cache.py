"""
A small bounded TTL cache of node health results, so DistributedRouter
doesn't re-probe a worker's /health on every single routing decision within
one agent task. Deliberately in-memory/per-process, not persisted -- health
is inherently a point-in-time signal, not something worth surviving a
restart.

Only ever consulted from the distributed-mode code path; single-node mode
never touches this module at all (see distributed_router.py's first check).
"""
import time
from dataclasses import dataclass
from typing import Dict, Optional

from app.services.model_registry import HealthState


@dataclass
class _CachedHealth:
    state: HealthState
    checked_at: float


class NodeHealthCache:
    def __init__(self, ttl_seconds: float):
        self._ttl_seconds = ttl_seconds
        self._entries: Dict[str, _CachedHealth] = {}

    def get(self, node_id: str) -> Optional[HealthState]:
        """Returns the cached state if still fresh, else None (meaning: the
        caller should probe and call set())."""
        entry = self._entries.get(node_id)
        if entry is None:
            return None
        if (time.monotonic() - entry.checked_at) > self._ttl_seconds:
            return None
        return entry.state

    def set(self, node_id: str, state: HealthState) -> None:
        self._entries[node_id] = _CachedHealth(state=state, checked_at=time.monotonic())

    def invalidate(self, node_id: str) -> None:
        """Called when a worker fails mid-execution (not just at a health
        probe) -- forces the next routing decision to re-probe rather than
        trust a HEALTHY result that just proved wrong."""
        self._entries.pop(node_id, None)


# Singleton, same convention as the other service-level registries.
node_health_cache = NodeHealthCache(ttl_seconds=None)


def _init_default_ttl() -> None:
    from app.config import settings
    node_health_cache._ttl_seconds = settings.NODE_HEALTH_CACHE_TTL_SECONDS


_init_default_ttl()
