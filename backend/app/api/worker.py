"""
Worker API -- what a SECOND SovereignX instance (e.g. "Laptop B" in 2 lap
sov) exposes for a primary node to call. This is the SAME codebase running
in a role, not a separate product: any SovereignX instance can serve as a
worker node for another, controlled entirely by configuration
(SOVEREIGN_DISTRIBUTED_MODE / AI_NODES_CONFIG on the primary, plus
NODE_SHARED_SECRET on both).

Security posture (industrial/on-prem, not a public API):
  - every route except /worker/health requires the shared-secret
    X-Node-Token header, verified against NODE_SHARED_SECRET
  - NODE_SHARED_SECRET unset means every authenticated route refuses --
    there is no "no auth" fallback
  - a request body over NODE_MAX_REQUEST_BYTES is rejected
  - the model call itself is bounded by the existing gateway timeout
    behavior (OllamaGateway's own httpx timeout)
  - no arbitrary code/shell endpoint is exposed here at all -- sandboxed
    execution stays local-only via LocalToolRegistry, never remote-callable
  - /worker/health deliberately returns no model/capability detail without
    auth, so an unauthenticated prober learns only "something is here"
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.gateway import get_gateway, ModelGateway
from app.gateway.exceptions import OllamaUnavailableError, ProviderExecutionError, ProviderInitializationError

logger = logging.getLogger("sovereignx")
router = APIRouter(prefix="/worker", tags=["worker"])


async def verify_node_token(x_node_token: Optional[str] = Header(None)):
    if not settings.NODE_SHARED_SECRET:
        raise HTTPException(
            status_code=503,
            detail="This node does not accept remote worker requests (NODE_SHARED_SECRET is not configured).",
        )
    if not x_node_token or x_node_token != settings.NODE_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing node token.")
    return True


class WorkerChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    options: Optional[Dict[str, Any]] = None


class WorkerChatResponse(BaseModel):
    content: str
    node_id: str = "local"


@router.get("/health")
async def worker_health():
    """Unauthenticated liveness probe only -- no model/capability info without a valid node token."""
    return {"status": "ok", "service": "sovereignx-worker"}


@router.get("/capabilities", dependencies=[Depends(verify_node_token)])
async def worker_capabilities():
    from app.services.model_registry import get_model_registry
    registry = get_model_registry()
    return {
        "node_id": "local",
        "models": [
            {
                "name": s.name,
                "capabilities": [c.value for c in s.capabilities],
                "health": s.health.value,
            }
            for s in registry.all_specs()
        ],
    }


@router.post("/chat", response_model=WorkerChatResponse, dependencies=[Depends(verify_node_token)])
async def worker_chat(
    body: WorkerChatRequest,
    request: Request,
    gateway: ModelGateway = Depends(get_gateway),
):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.NODE_MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="Request body exceeds the configured size limit.")

    try:
        answer = await gateway.chat_completion(body.messages, options=body.options)
        return WorkerChatResponse(content=answer, node_id="local")
    except (OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError) as e:
        raise HTTPException(status_code=503, detail=f"Worker model unavailable: {str(e)}")
    except Exception as e:
        logger.error(f"worker_chat failed: {e}")
        raise HTTPException(status_code=502, detail=f"Worker model call failed: {str(e)}")
