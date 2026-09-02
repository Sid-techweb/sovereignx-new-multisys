"""
SovereignX worker service -- the "Node B" side of 2 Lap Sov. A deliberately
small, standalone FastAPI app, run as its own process on its own port, NOT
mounted into app.main. A worker does not need the frontend, chat history,
document DB, pgvector, or the four-agent investigation pipeline -- it only
needs to accept authenticated execution requests from a trusted SovereignX
Core node and run them in the same Docker sandbox used locally.

Run with (see docs/2_LAP_SOV_WORKER_SETUP.md for the full handoff guide):
    uvicorn app.worker.main:app --host 127.0.0.1 --port 9001

Binds to 127.0.0.1 only in this phase -- see NODE_ID/AI_NODES_CONFIG in
app/config.py for how a real second machine's private-LAN address replaces
127.0.0.1 later purely through configuration, no code change.
"""
import logging

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.sandbox import SandboxUnavailableError, execute_python_sandboxed
from app.worker.auth import require_node_auth
from app.worker.schemas import (
    SUPPORTED_LANGUAGES,
    CapabilitiesResponse,
    ExecuteCodeRequest,
    ExecuteCodeResponse,
    HealthResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sovereignx")

app = FastAPI(title="SovereignX Worker", version="0.1.0")

# This worker's real, currently-implemented capabilities. Deliberately does
# NOT include CODING/VISION/GENERAL_CHAT/MODEL_INFERENCE -- this worker
# executes code, it does not generate it or run any model. Kept as plain
# strings (not the ModelCapability enum) so the wire contract stays a
# simple, dependency-free JSON list a non-Python worker implementation
# could also produce.
WORKER_CAPABILITIES = ["SANDBOX_EXECUTION"]


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", response_model=HealthResponse)
async def health():
    """Unauthenticated by design, matching the main app's own GET /health
    (app/api/health.py) -- a liveness probe reveals no secrets and nothing
    an unauthenticated caller couldn't already infer from the TCP connect
    succeeding."""
    return HealthResponse(node_id=settings.NODE_ID, status="healthy", role="worker", ready=True)


@app.get("/capabilities", response_model=CapabilitiesResponse, dependencies=[Depends(require_node_auth)])
async def capabilities():
    return CapabilitiesResponse(node_id=settings.NODE_ID, capabilities=WORKER_CAPABILITIES)


@app.post("/execute-code", response_model=ExecuteCodeResponse, dependencies=[Depends(require_node_auth)])
async def execute_code(request: ExecuteCodeRequest):
    if request.language not in SUPPORTED_LANGUAGES:
        return JSONResponse(
            status_code=422,
            content={"detail": f"Unsupported language '{request.language}'. Supported: {sorted(SUPPORTED_LANGUAGES)}."},
        )

    try:
        result = execute_python_sandboxed(request.code, timeout_seconds=request.timeout_seconds)
    except SandboxUnavailableError as e:
        logger.error(f"worker execute-code: sandbox unavailable: {e}")
        return JSONResponse(status_code=503, content={"detail": str(e)})

    logger.info(
        f"worker execute-code node={settings.NODE_ID} exit_code={result['exit_code']} "
        f"timed_out={result['timed_out']} elapsed_ms={result['elapsed_ms']}"
    )
    return ExecuteCodeResponse(
        success=(result["exit_code"] == 0 and not result["timed_out"]),
        exit_code=result["exit_code"],
        stdout=result["stdout"],
        stderr=result["stderr"],
        timed_out=result["timed_out"],
        elapsed_ms=result["elapsed_ms"],
    )
