"""
Node registry -- the foundation for "2 lap sov" (SovereignX distributed
across two trusted on-prem machines over the private LAN) without requiring
a second physical machine to exist for the code to be correct.

Two 6GB GPUs do not become one 12GB GPU: this is DISTRIBUTED TASK
execution (capability-aware routing to whichever node/model can do the
job), never cross-node tensor/model parallelism. A node is just "a place
some of the ModelSpecs in model_registry.py actually run" -- the registry
itself has no opinion about what's on it beyond that.

SOVEREIGN_DISTRIBUTED_MODE=false (the default) means exactly one node
("local") exists and every capability resolves to it -- current,
already-verified single-workstation behavior is completely unchanged.
Setting it True and providing AI_NODES_CONFIG adds more nodes; it can
never remove "local", so single-node operation is not a special case to
maintain separately, it's just the zero-remote-nodes case of the same code
path.

Trust boundary: only URLs matching a node registered here (host+port,
loaded from config, never hardcoded) are ever treated as trusted-LAN
targets for outbound calls or for the sovereignty monitor's classification
-- see classify_network_target() and app/services/sovereignty.py. An
unconfigured private IP is NOT automatically trusted just because it's
RFC1918; only an approved, configured node is.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger("sovereignx")

LOCAL_NODE_ID = "local"


class NodeHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class NetworkTarget(str, Enum):
    LOCAL_PROCESS = "LOCAL_PROCESS"  # no network call at all (in-process function call)
    LOCALHOST = "LOCALHOST"          # loopback HTTP call (127.0.0.1 / localhost) on this machine
    PRIVATE_LAN = "PRIVATE_LAN"      # a CONFIGURED, approved SovereignX node over the private network
    EXTERNAL = "EXTERNAL"            # anything else -- including an unconfigured private IP


@dataclass
class NodeSpec:
    node_id: str
    url: str  # base URL of this node's worker API, e.g. "http://192.168.1.50:8100"
    role: str = "secondary"  # "primary" | "secondary"
    models: List[str] = field(default_factory=list)
    health: NodeHealth = NodeHealth.UNKNOWN
    last_checked_at: Optional[float] = None
    last_error: Optional[str] = None


def _load_nodes_from_config() -> List[NodeSpec]:
    """
    AI_NODES_CONFIG is either a JSON array string or a path to a JSON file
    containing one, e.g.:
        [{"node_id": "node_b", "url": "http://192.168.1.50:8100",
          "role": "secondary", "models": ["qwen3.5:4b"]}]
    No IPs/hostnames are ever hardcoded in code -- if this is empty or
    unparseable, distributed mode simply has zero remote nodes registered
    (the "local" node still always exists -- see NodeRegistry.__init__).
    """
    raw = settings.AI_NODES_CONFIG.strip()
    if not raw:
        return []

    if not raw.startswith("["):
        # Treat as a file path.
        path = Path(raw)
        if not path.exists():
            logger.warning(f"AI_NODES_CONFIG path does not exist: {raw}")
            return []
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read AI_NODES_CONFIG file {raw}: {e}")
            return []

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"AI_NODES_CONFIG is not valid JSON: {e}")
        return []

    nodes = []
    for entry in entries:
        try:
            nodes.append(NodeSpec(
                node_id=entry["node_id"],
                url=entry["url"].rstrip("/"),
                role=entry.get("role", "secondary"),
                models=entry.get("models", []),
            ))
        except (KeyError, TypeError) as e:
            logger.error(f"Skipping malformed AI_NODES_CONFIG entry {entry!r}: {e}")
    return nodes


class NodeRegistry:
    def __init__(self):
        self._nodes: Dict[str, NodeSpec] = {
            LOCAL_NODE_ID: NodeSpec(node_id=LOCAL_NODE_ID, url="", role="primary", health=NodeHealth.HEALTHY)
        }
        if settings.SOVEREIGN_DISTRIBUTED_MODE:
            for node in _load_nodes_from_config():
                self._nodes[node.node_id] = node
                logger.info(f"Registered remote SovereignX node: {node.node_id} ({node.url})")

    def get(self, node_id: str) -> Optional[NodeSpec]:
        return self._nodes.get(node_id)

    def list_nodes(self) -> List[NodeSpec]:
        return list(self._nodes.values())

    def remote_nodes(self) -> List[NodeSpec]:
        return [n for n in self._nodes.values() if n.node_id != LOCAL_NODE_ID]

    def trusted_hosts(self) -> List[str]:
        """Hostnames/IPs of every configured node -- fed into the sovereignty
        monitor's trusted-host set so legitimate node-to-node LAN traffic is
        never misclassified as an external/alert connection."""
        hosts = []
        for node in self._nodes.values():
            if not node.url:
                continue
            parsed = urlparse(node.url)
            if parsed.hostname:
                hosts.append(parsed.hostname.lower())
        return hosts

    def check_health(self, node_id: str, timeout: float = 3.0) -> NodeHealth:
        """
        Best-effort health probe against a remote node's /health endpoint.
        Never raises -- an unreachable node becomes OFFLINE, not a crash.
        The 'local' node is always HEALTHY (it's this process).
        """
        node = self._nodes.get(node_id)
        if node is None:
            return NodeHealth.UNKNOWN
        if node_id == LOCAL_NODE_ID:
            node.health = NodeHealth.HEALTHY
            return node.health

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"{node.url}/health")
            node.health = NodeHealth.HEALTHY if resp.status_code == 200 else NodeHealth.DEGRADED
            node.last_error = None
        except Exception as e:
            node.health = NodeHealth.OFFLINE
            node.last_error = str(e)
        node.last_checked_at = time.time()
        return node.health


def classify_network_target(url_or_host: str, node_registry: Optional[NodeRegistry] = None) -> NetworkTarget:
    """
    Classifies an outbound network target for sovereignty reporting.
    Order matters: localhost/loopback first (always trusted regardless of
    node config), then configured-node membership (PRIVATE_LAN), then
    everything else -- including an unconfigured RFC1918 address, which is
    deliberately NOT auto-trusted (see module docstring).
    """
    host = url_or_host
    if "://" in url_or_host:
        parsed = urlparse(url_or_host)
        host = parsed.hostname or parsed.netloc
    if host and ":" in host and not host.count(":") > 1:  # strip a bare host:port, leave IPv6 alone
        host = host.split(":")[0]
    if not host:
        return NetworkTarget.EXTERNAL

    host_lower = host.lower()
    if host_lower in ("localhost", "127.0.0.1", "::1"):
        return NetworkTarget.LOCALHOST

    registry = node_registry or get_node_registry()
    if host_lower in registry.trusted_hosts():
        return NetworkTarget.PRIVATE_LAN

    return NetworkTarget.EXTERNAL


_registry_instance: Optional[NodeRegistry] = None


def get_node_registry() -> NodeRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = NodeRegistry()
    return _registry_instance


def reset_node_registry_for_testing() -> None:
    global _registry_instance
    _registry_instance = None
