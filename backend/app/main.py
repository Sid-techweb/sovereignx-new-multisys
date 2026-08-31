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

# Preload/initialize BGE-M3 embedding model exactly once at application startup.
# BGE-M3 runs in an isolated worker process (see app/rag/embedding_worker_manager.py):
# a native PyTorch fault there cannot terminate this FastAPI process. This call
# spawns that worker and waits (bounded) for it to report ready; failure here is
# intentionally non-fatal to backend startup -- embeddings/DOCUMENT_RAG degrade to
# a clean error, but GENERAL_CHAT and the rest of the backend remain unaffected.
@app.on_event("startup")
def startup_event():
    logger.info("FastAPI startup: spawning isolated BGE-M3 embedding worker...")
    try:
        from app.rag.embeddings import BGEM3EmbeddingProvider
        BGEM3EmbeddingProvider().initialize()
        logger.info("FastAPI startup: BGE-M3 embedding worker ready.")
    except Exception as e:
        logger.error(f"FastAPI startup: BGE-M3 embedding worker not ready: {e}")


@app.on_event("shutdown")
def shutdown_event():
    logger.info("FastAPI shutdown: stopping BGE-M3 embedding worker...")
    try:
        from app.rag.embedding_worker_manager import get_worker_manager
        from app.config import settings as _settings
        get_worker_manager(_settings.EMBEDDING_MODEL).shutdown()
    except Exception as e:
        logger.warning(f"FastAPI shutdown: error stopping BGE-M3 embedding worker: {e}")

