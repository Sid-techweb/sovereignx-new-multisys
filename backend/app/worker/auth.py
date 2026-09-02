"""
Machine-to-machine authentication for the worker service. Deliberately a
separate mechanism from the main app's user-facing auth (app/api/auth.py,
X-API-Key / JWT) -- a worker node authenticates SovereignX Core, not a
human, and must never accept the same demo API key used for the frontend.

NODE_SHARED_SECRET is the only credential. Two failure modes are treated
distinctly on purpose:
  - the SERVER has no secret configured (NODE_SHARED_SECRET == "") -> every
    execution request is refused, regardless of what header is sent. An
    unset secret must never silently mean "any caller is trusted".
  - the CALLER sends a missing/wrong header -> 401.
"""
import hmac
import logging

from fastapi import Header, HTTPException, status

from app.config import settings

logger = logging.getLogger("sovereignx")

NODE_KEY_HEADER = "X-Sovereign-Node-Key"


async def require_node_auth(
    x_sovereign_node_key: str = Header(default=None, alias=NODE_KEY_HEADER),
) -> None:
    if not settings.NODE_SHARED_SECRET:
        logger.warning(
            "worker_auth: execution request refused -- NODE_SHARED_SECRET is not configured on this worker."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This worker has no NODE_SHARED_SECRET configured; execution endpoints are unavailable.",
        )

    if not x_sovereign_node_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing node authentication header.")

    # Constant-time comparison -- avoids leaking secret length/prefix via
    # response-timing differences on a request an attacker fully controls.
    if not hmac.compare_digest(x_sovereign_node_key, settings.NODE_SHARED_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid node authentication key.")
