"""
Capability -> node selection for distributed execution. Generic on purpose:
nothing here says "laptop 2" or hardcodes a node count -- it asks
NodeRegistry which registered nodes offer a capability and picks a healthy
one, whether that's Node B today or Node C/D added later purely through
AI_NODES_CONFIG.

Only ever invoked from the distributed-mode branch of a tool's execution
path (see app/services/agent_tools.py::execute_python) -- single-node mode
short-circuits before this module is imported into the call path at all,
so it makes zero probes/health checks/remote calls by construction, not by
convention.
"""
import logging
import time
from dataclasses import dataclass
from typing import Optional

from app.config import settings
from app.services.model_registry import HealthState, ModelCapability
from app.services.node_health_cache import node_health_cache
from app.services.node_registry import LOCAL_NODE_ID, NodeRegistry, NodeSpec, classify_node_scope
from app.services.node_registry import node_registry as default_node_registry
from app.services.worker_client import WorkerClient, WorkerError

logger = logging.getLogger("sovereignx")


class CapabilityUnavailableError(Exception):
    """No node -- local or remote -- currently offers the requested capability.
    Never silently redirected to an unrelated node; the caller must surface
    this as a real failure."""


@dataclass
class RoutingDecision:
    scope: str  # "LOCAL" | "REMOTE"
    node_id: str
    node_url: Optional[str]
    execution_scope: str  # LOCAL / LOCALHOST / PRIVATE_LAN / UNTRUSTED (see node_registry.classify_node_scope)
    is_fallback: bool
    reason: str
    selection_ms: float
    health_ms: float


class DistributedRouter:
    def __init__(self, registry: Optional[NodeRegistry] = None, health_cache=None):
        self._registry = registry if registry is not None else default_node_registry
        self._health_cache = health_cache if health_cache is not None else node_health_cache

    def _probe_health(self, node: NodeSpec) -> HealthState:
        try:
            with WorkerClient(
                node.url,
                settings.NODE_SHARED_SECRET,
                connect_timeout_seconds=settings.WORKER_CONNECT_TIMEOUT_SECONDS,
                read_timeout_seconds=settings.WORKER_READ_TIMEOUT_SECONDS,
            ) as client:
                health = client.health()
            state = HealthState.HEALTHY if (health.status == "healthy" and health.ready) else HealthState.DEGRADED
        except WorkerError as e:
            logger.warning(f"distributed_router: health probe failed for node={node.node_id}: {e}")
            state = HealthState.OFFLINE
        self._health_cache.set(node.node_id, state)
        self._registry.set_health(node.node_id, state)
        return state

    def _get_health(self, node: NodeSpec) -> HealthState:
        """First call for a node probes (cache miss); calls within the TTL
        window reuse the cached result; an expired entry re-probes."""
        cached = self._health_cache.get(node.node_id)
        if cached is not None:
            return cached
        return self._probe_health(node)

    def route_sandbox_execution(self) -> RoutingDecision:
        t_select0 = time.perf_counter()
        capability = ModelCapability.SANDBOX_EXECUTION

        candidates = [n for n in self._registry.find_by_capability(capability) if n.node_id != LOCAL_NODE_ID]

        health_ms = 0.0
        for node in candidates:
            t_health0 = time.perf_counter()
            health = self._get_health(node)
            health_ms += (time.perf_counter() - t_health0) * 1000.0
            if health == HealthState.HEALTHY:
                selection_ms = (time.perf_counter() - t_select0) * 1000.0
                return RoutingDecision(
                    scope="REMOTE",
                    node_id=node.node_id,
                    node_url=node.url,
                    execution_scope=classify_node_scope(node.node_id, node.url, self._registry),
                    is_fallback=False,
                    reason=f"selected healthy worker node '{node.node_id}'",
                    selection_ms=round(selection_ms, 2),
                    health_ms=round(health_ms, 2),
                )

        local = self._registry.get(LOCAL_NODE_ID)
        selection_ms = (time.perf_counter() - t_select0) * 1000.0
        if local and capability in local.capabilities:
            reason = (
                "no compatible remote worker configured; local node supports the capability"
                if not candidates
                else "no healthy remote worker available; local node supports the capability"
            )
            logger.warning(f"distributed_router: {reason} -- falling back to local sandbox.")
            return RoutingDecision(
                scope="LOCAL",
                node_id=LOCAL_NODE_ID,
                node_url=local.url,
                execution_scope="LOCAL",
                is_fallback=True,
                reason=reason,
                selection_ms=round(selection_ms, 2),
                health_ms=round(health_ms, 2),
            )

        raise CapabilityUnavailableError("No node -- local or remote -- currently offers SANDBOX_EXECUTION.")


distributed_router = DistributedRouter()
