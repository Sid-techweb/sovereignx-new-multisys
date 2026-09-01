import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import logging
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import health, models, agents, documents, rag, tools, reports, sovereignty, cases, chat
from app.api.auth import verify_api_key
from app.services.sovereignty import apply_monkeypatching
apply_monkeypatching()
from app.gateway.exceptions import (
    UnsupportedProviderError,
    OllamaUnavailableError,
    ProviderInitializationError,
    ProviderExecutionError
)
from app.rag.exceptions import (
    EmbeddingModelUnavailableError,
    DatabaseConnectionError,
    IndexingError,
    SearchQueryError
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


# Setup basic structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sovereignx")

# Try to initialize database tables on startup
try:
    from app.database import engine, Base
    from app.rag.models import SQLDocumentChunk
    from app.models.cases_reports import SQLCase, SQLReportRecord
    from app.chat.models import ChatConversation, ChatMessage
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)
    
    # Safe PostgreSQL column migrations for pre-existing tables
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS requires_human_review BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS escalation_reason TEXT;"))
        # E5 embedding migration (additive, non-destructive): a second,
        # separate 384-dim vector column alongside the existing BGE-M3
        # `embedding` column -- see rag/models.py for why this is a new
        # column rather than resizing/replacing the existing one.
        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_e5 vector(384);"))
        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_e5_model VARCHAR(128);"))

    logger.info("PostgreSQL database tables initialized/verified successfully.")
except Exception as e:
    logger.warning(
        f"Database table initialization failed. If PostgreSQL is offline, run pgvector container: {str(e)}"
    )

def get_cors_headers(request) -> dict:
    origin = request.headers.get("origin")
    headers = {}
    if origin in settings.ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers

app = FastAPI(
    title="SovereignX Backend API",
    description="Phase 1 Foundation & Model Gateway for MRPL Problem Statement SIH26117",
    version="1.0.0"
)

# Exception handlers to avoid exposing raw stack traces to client
@app.exception_handler(UnsupportedProviderError)
async def unsupported_provider_handler(request, exc):
    logger.error(f"Unsupported model provider: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers=get_cors_headers(request)
    )

@app.exception_handler(OllamaUnavailableError)
async def ollama_unavailable_handler(request, exc):
    logger.error(f"Ollama unavailable or offline: {exc}")
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers=get_cors_headers(request)
    )

@app.exception_handler(ProviderInitializationError)
async def provider_initialization_handler(request, exc):
    logger.error(f"Provider initialization failed: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers=get_cors_headers(request)
    )

@app.exception_handler(ProviderExecutionError)
async def provider_execution_handler(request, exc):
    logger.error(f"Provider execution failed: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers=get_cors_headers(request)
    )

@app.exception_handler(EmbeddingModelUnavailableError)
async def embedding_model_unavailable_handler(request, exc):
    logger.error(f"Embedding model unavailable: {exc}")
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers=get_cors_headers(request)
    )

@app.exception_handler(DatabaseConnectionError)
async def database_connection_handler(request, exc):
    logger.error(f"Database connection error: {exc}")
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers=get_cors_headers(request)
    )

@app.exception_handler(IndexingError)
async def indexing_error_handler(request, exc):
    logger.error(f"Indexing error: {exc}")
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
        headers=get_cors_headers(request)
    )

@app.exception_handler(SearchQueryError)
async def search_query_error_handler(request, exc):
    logger.error(f"Search query error: {exc}")
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
        headers=get_cors_headers(request)
    )

@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request, exc):
    logger.error(f"HTTP exception: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=get_cors_headers(request)
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
        headers=get_cors_headers(request)
    )


# Configure CORS for local development (Vite dev server) and future environments
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health.router)
app.include_router(models.router, dependencies=[Depends(verify_api_key)])
app.include_router(agents.router, dependencies=[Depends(verify_api_key)])
app.include_router(documents.router, dependencies=[Depends(verify_api_key)])
app.include_router(rag.router, dependencies=[Depends(verify_api_key)])
app.include_router(tools.router, dependencies=[Depends(verify_api_key)])
app.include_router(reports.router, dependencies=[Depends(verify_api_key)])
app.include_router(cases.router, dependencies=[Depends(verify_api_key)])
app.include_router(chat.router, dependencies=[Depends(verify_api_key)])
app.include_router(sovereignty.router)

# LIVENESS vs READINESS (Phase 14-16 of the E5 embedding migration).
#
# The old design loaded BGE-M3 synchronously inside this startup event --
# measured at ~18.5s cold -- during which FastAPI/Uvicorn serves NOTHING,
# including /health, because the ASGI app does not begin accepting requests
# until every @app.on_event("startup") handler returns. That made basic
# process liveness indistinguishable from AI-model readiness.
#
# This version returns almost immediately (so /health responds right away)
# and instead kicks off background warmup threads for the LLM (Qwen, via
# Ollama) and the configured embedding provider (BGE-M3 or E5, via
# get_embedding_provider() -- never hardcoded here). Progress is tracked in
# app.services.readiness and surfaced via GET /models; chat/service.py gives
# an in-flight warmup a short bounded wait rather than proceeding blind (see
# _prepare_turn). Both warmups run IN PARALLEL: they occupy largely
# independent resources (Qwen lives in Ollama's separate llama-server
# process/VRAM; the embedding provider lives in this process's own RAM), and
# this was measured, not assumed -- see the migration report's "Parallel
# Warmup" section for the actual wall-clock/peak-RAM/peak-commit numbers.
@app.on_event("startup")
def startup_event():
    import threading
    from app.services import readiness

    readiness.mark_warmup_started()
    logger.info(
        "FastAPI startup: liveness ready immediately; starting background "
        f"model warmup (llm={settings.MODEL_NAME}, embedding_provider={settings.EMBEDDING_PROVIDER})..."
    )

    def _warm_llm():
        try:
            import httpx
            with httpx.Client(timeout=120.0) as client:
                client.post(
                    f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                    json={
                        "model": settings.MODEL_NAME,
                        "messages": [{"role": "user", "content": "Hi"}],
                        "stream": False,
                        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
                        **({"think": settings.OLLAMA_THINK} if settings.OLLAMA_THINK is not None else {}),
                    },
                )
            readiness.mark_llm_ready()
            logger.info("Background warmup: LLM ready.")
        except Exception as e:
            readiness.mark_llm_ready(error=str(e))
            logger.error(f"Background warmup: LLM warmup failed (non-fatal): {e}")

    def _warm_embedding():
        try:
            from app.rag.embeddings import get_embedding_provider
            get_embedding_provider().initialize()
            readiness.mark_embedding_ready()
            logger.info(f"Background warmup: {settings.EMBEDDING_PROVIDER} embedding provider ready.")
        except Exception as e:
            readiness.mark_embedding_ready(error=str(e))
            logger.error(
                f"Background warmup: {settings.EMBEDDING_PROVIDER} embedding provider not ready (non-fatal): {e}"
            )

    threading.Thread(target=_warm_llm, daemon=True, name="warmup-llm").start()
    threading.Thread(target=_warm_embedding, daemon=True, name="warmup-embedding").start()


@app.on_event("shutdown")
def shutdown_event():
    logger.info("FastAPI shutdown: stopping any active embedding worker process(es)...")
    from app.rag.embedding_worker_manager import get_worker_manager
    # Shut down both provider slots defensively -- shutdown() on a manager
    # that never spawned a process is a safe no-op, and BGE stays available
    # as a fallback (Phase 3) so its worker may be live even when E5 is the
    # active EMBEDDING_PROVIDER.
    for provider in ("bge", "e5"):
        try:
            get_worker_manager(provider, settings.EMBEDDING_MODEL).shutdown()
        except Exception as e:
            logger.warning(f"FastAPI shutdown: error stopping {provider} embedding worker: {e}")

