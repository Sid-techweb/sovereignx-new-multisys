"""
HTTP client for calling a remote SovereignX node's worker API
(app/api/worker.py running on that node). Every call target is a NodeSpec
already loaded from AI_NODES_CONFIG -- this module never accepts or
constructs an arbitrary URL, only ever dials a pre-registered, approved node.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.services.node_registry import NodeSpec

logger = logging.getLogger("sovereignx")


class WorkerCallError(Exception):
    pass


async def call_remote_worker_chat(
    node: NodeSpec,
    messages: List[Dict[str, str]],
    options: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> str:
    """
    Calls POST {node.url}/worker/chat with the shared-secret node token.
    Raises WorkerCallError (never a raw httpx exception) so callers have one
    exception type to catch regardless of whether the failure was a
    connection error, a timeout, or a non-200 response.
    """
    if not settings.NODE_SHARED_SECRET:
        raise WorkerCallError("NODE_SHARED_SECRET is not configured -- cannot authenticate to a remote node.")

    timeout = timeout or settings.NODE_REQUEST_TIMEOUT_SECONDS
    url = f"{node.url}/worker/chat"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json={"messages": messages, "options": options},
                headers={"X-Node-Token": settings.NODE_SHARED_SECRET},
            )
        if resp.status_code != 200:
            raise WorkerCallError(f"Node {node.node_id} returned HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data["content"]
    except httpx.TimeoutException as e:
        raise WorkerCallError(f"Node {node.node_id} timed out after {timeout}s: {e}") from e
    except httpx.RequestError as e:
        raise WorkerCallError(f"Node {node.node_id} unreachable: {e}") from e
