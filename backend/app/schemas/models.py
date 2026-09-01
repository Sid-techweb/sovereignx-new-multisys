from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ModelInfoResponse(BaseModel):
    provider: str
    model: str
    status: str
    # Reported separately from LLM `status` above: the embedding worker is
    # an independent subsystem (see app/rag/embedding_worker_manager.py).
    # A degraded/crashed embedding worker must never be conflated with the
    # LLM/backend being down -- GENERAL_CHAT does not depend on it.
    embedding_worker_status: Optional[str] = None
    embedding_worker_pid: Optional[int] = None
    # Which embedding provider is currently active ("bge" | "e5") and
    # background-warmup readiness for both models (Phase 14-16 of the E5
    # migration) -- see app/services/readiness.py. Distinct from `status`
    # above (LLM/backend liveness): a model can be alive but not yet warm.
    embedding_provider: Optional[str] = None
    llm_ready: Optional[bool] = None
    embedding_ready: Optional[bool] = None

class GroundedQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Question to ask the grounded model")

class GroundedQueryResponse(BaseModel):
    query: str
    answer: str
    retrieved_chunks: List[Dict[str, Any]]
    model_used: str
    latency_ms: float
