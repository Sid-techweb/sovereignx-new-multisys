"""
Node registry -- a catalog of which SovereignX instances ("nodes": this
machine, plus eventually other on-prem devices like a second laptop) exist,
what they expose, and their health. Foundation only: nothing yet routes a
real request to a remote node, and no worker API/client exists yet (that is
explicitly P1, not this phase -- see the module docstring in
app/services/model_registry.py for the same boundary on the model side).

Single-node is the only mode actually exercised: when
settings.SOVEREIGN_DISTRIBUTED_MODE is False (the default), this registry
holds exactly one node -- LOCAL_NODE_ID, pointed at this process's own
settings.OLLAMA_BASE_URL -- and never parses AI_NODES_CONFIG or makes any
remote call. Turning distributed mode on only changes what this registry
*knows about*; it still performs no remote I/O by itself.
"""
import ipaddress
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse

from app.services.model_registry import HealthState, ModelCapability, LOCAL_NODE_ID

logger = logging.getLogger("sovereignx")


@dataclass
class NodeSpec:
    node_id: str
    url: str
    role: str = "primary"  # "primary" | "worker"
    models: List[str] = field(default_factory=list)
    capabilities: List[ModelCapability] = field(default_factory=list)
    health: HealthState = HealthState.UNKNOWN


class NodeRegistry:
    def __init__(self):
        self._nodes: Dict[str, NodeSpec] = {}

    def register(self, spec: NodeSpec) -> None:
        self._nodes[spec.node_id] = spec
        logger.info(
            f"node_registry: registered node '{spec.node_id}' role={spec.role} "
            f"url={spec.url} models={spec.models}"
        )

    def get(self, node_id: str) -> Optional[NodeSpec]:
        return self._nodes.get(node_id)

    def list_nodes(self) -> List[NodeSpec]:
        return list(self._nodes.values())

    def set_health(self, node_id: str, health: HealthState) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].health = health

    def find_by_capability(self, capability: ModelCapability) -> List[NodeSpec]:
        return [n for n in self._nodes.values() if capability in n.capabilities and n.health != HealthState.OFFLINE]

    def is_distributed(self) -> bool:
        return len(self._nodes) > 1


def _parse_ai_nodes_config(raw: str) -> List[NodeSpec]:
    """
    AI_NODES_CONFIG shape: a JSON array of objects, e.g.
        [{"node_id": "laptop-2", "url": "http://192.168.1.50:8000",
          "role": "worker", "models": ["qwen2.5:7b"],
          "capabilities": ["GENERAL_CHAT", "CODING"]}]
    Never contains a hardcoded IP as a Python literal in this codebase --
    it is operator-supplied configuration (env var / .env), consistent with
    how TRUSTED_HOSTS_DEV documents the same rule in app/services/sovereignty.py.
    Malformed entries are skipped with a warning rather than raising --
    a config typo in one worker definition shouldn't crash node registry
    initialization for the rest.
    """
    nodes: List[NodeSpec] = []
    if not raw or not raw.strip():
        return nodes
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"node_registry: AI_NODES_CONFIG is not valid JSON, ignoring: {e}")
        return nodes
    if not isinstance(parsed, list):
        logger.error("node_registry: AI_NODES_CONFIG must be a JSON array, ignoring.")
        return nodes
    for entry in parsed:
        try:
            node_id = entry["node_id"]
            url = entry["url"]
            capabilities = [ModelCapability(c) for c in entry.get("capabilities", [])]
            nodes.append(NodeSpec(
                node_id=node_id,
                url=url,
                role=entry.get("role", "worker"),
                models=list(entry.get("models", [])),
                capabilities=capabilities,
                health=HealthState.UNKNOWN,
            ))
        except (KeyError, ValueError) as e:
            logger.warning(f"node_registry: skipping malformed AI_NODES_CONFIG entry {entry!r}: {e}")
    return nodes


def _build_default_registry() -> NodeRegistry:
    from app.config import settings

    registry = NodeRegistry()

    registry.register(NodeSpec(
        node_id=LOCAL_NODE_ID,
        url=settings.OLLAMA_BASE_URL,
        role="primary",
        models=[settings.MODEL_NAME] if settings.MODEL_NAME else [],
        capabilities=[
            ModelCapability.GENERAL_CHAT,
            ModelCapability.RAG_GENERATION,
            ModelCapability.CODING,
            ModelCapability.REASONING,
            ModelCapability.VISION,
            ModelCapability.OCR,
            ModelCapability.REPORT_GENERATION,
            ModelCapability.SANDBOX_EXECUTION,
        ],
        health=HealthState.UNKNOWN,
    ))

    if not settings.SOVEREIGN_DISTRIBUTED_MODE:
        # Deliberately stop here: no AI_NODES_CONFIG parsing, no remote
        # probing of any kind, in the default single-node deployment.
        return registry

    for node in _parse_ai_nodes_config(settings.AI_NODES_CONFIG):
        registry.register(node)

    return registry


# Singleton instance, same convention as model_registry.model_registry and
# tools.tool_registry.
node_registry = _build_default_registry()


def classify_node_scope(node_id: str, url: str, registry: Optional[NodeRegistry] = None) -> str:
    """
    Sovereignty classification for the audit trail (execution_scope field) --
    deliberately conservative: an RFC1918 private-range host is classified
    PRIVATE_LAN only when it is an ALREADY-REGISTERED NodeSpec (i.e. came
    from AI_NODES_CONFIG, operator-supplied), never merely because the IP
    happens to look private. Encountering a private IP for a node_id that
    isn't in the registry -- which the normal routing path never does,
    since DistributedRouter only ever contacts registered NodeSpecs -- is
    classified UNTRUSTED, not silently upgraded to sovereign just because
    the address is non-routable on the public internet.

    Returns one of: "LOCAL" (the in-process default node, no network hop
    at all), "LOCALHOST" (a separate worker process on the same machine),
    "PRIVATE_LAN" (a registered node on a private-range address), or
    "UNTRUSTED".
    """
    if node_id == LOCAL_NODE_ID:
        return "LOCAL"

    registry = registry if registry is not None else node_registry
    is_registered = registry.get(node_id) is not None

    hostname = urlparse(url).hostname or ""
    hostname = hostname.strip("[]")  # IPv6 literals in a URL are bracketed

    if hostname in ("localhost", "127.0.0.1", "::1"):
        return "LOCALHOST"

    if is_registered:
        try:
            if ipaddress.ip_address(hostname).is_private:
                return "PRIVATE_LAN"
        except ValueError:
            pass  # not a bare IP literal (e.g. a hostname) -- falls through to UNTRUSTED

    return "UNTRUSTED"
