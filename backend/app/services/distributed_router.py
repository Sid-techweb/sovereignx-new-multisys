"""
Capability-based task/model routing across nodes -- the "2 lap sov" request
path. NOT round-robin load balancing: a capability resolves to the
best-priority model that declares it, wherever it lives (local or a
registered remote node), with automatic failover to the next candidate
(never a silent wrong-capability substitution) if that node is unreachable.

Foundation module: built and unit-tested against a mocked remote node
(no second physical machine required for correctness), but NOT yet wired
into chat/service.py's live request path -- see the migration report for
why (SOVEREIGN_DISTRIBUTED_MODE defaults to False, so today's single-node
behavior is provably unaffected either way; wiring this into the
extensively-tested existing chat pipeline is deferred until live
two-machine validation is possible).
"""
import logging
from typing import Any, Dict, List, Optional

from app.gateway import get_gateway
from app.services.model_registry import Capability, ModelSpec, get_model_registry
from app.services.node_registry import LOCAL_NODE_ID, NodeHealth, get_node_registry
from app.services.worker_client import WorkerCallError, call_remote_worker_chat

logger = logging.getLogger("sovereignx")


class CapabilityUnavailableError(Exception):
    """
    Raised only when NO candidate model/node (local or remote) could serve
    the requested capability. Callers MUST treat this as an explicit
    "capability temporarily unavailable" state -- never fall back to
    answering with a model that doesn't actually have this capability.
    """
    pass


async def route_capability_request(
    capability: Capability,
    messages: List[Dict[str, str]],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Selects, in priority order, every ModelSpec that declares `capability`,
    tries each one's node in turn, and returns the first success. A remote
    node's health is checked before calling it (bounded timeout, never
    raises) so an offline Node B is skipped rather than hung on.

    Returns {"content": str, "node_id": str, "model": str}.
    Raises CapabilityUnavailableError if every candidate failed/was offline.
    """
    model_registry = get_model_registry()
    node_registry = get_node_registry()

    candidates: List[ModelSpec] = model_registry.select_all_capable(capability)
    if not candidates:
        raise CapabilityUnavailableError(f"No model is registered for capability '{capability.value}'.")

    last_error: Optional[str] = None
    for spec in candidates:
        node = node_registry.get(spec.node_id)
        if node is None:
            logger.warning(f"route_capability_request: spec {spec.name} references unknown node {spec.node_id}, skipping")
            continue

        if spec.node_id == LOCAL_NODE_ID:
            try:
                gateway = get_gateway()
                content = await gateway.chat_completion(messages, options)
                return {"content": content, "node_id": LOCAL_NODE_ID, "model": spec.name}
            except Exception as e:
                last_error = f"local model {spec.name} failed: {e}"
                logger.warning(f"route_capability_request: {last_error}")
                continue

        # Remote node: check health first so an offline node is a clean
        # skip-and-failover, not a hung request.
        health = node_registry.check_health(spec.node_id)
        if health == NodeHealth.OFFLINE:
            last_error = f"node {spec.node_id} is OFFLINE"
            logger.warning(f"route_capability_request: {last_error}, failing over")
            continue

        try:
            content = await call_remote_worker_chat(node, messages, options)
            return {"content": content, "node_id": spec.node_id, "model": spec.name}
        except WorkerCallError as e:
            last_error = str(e)
            logger.warning(f"route_capability_request: node {spec.node_id} call failed: {e}, failing over")
            continue

    raise CapabilityUnavailableError(
        f"Capability '{capability.value}' is temporarily unavailable: all {len(candidates)} "
        f"candidate model(s)/node(s) failed. Last error: {last_error}"
    )
