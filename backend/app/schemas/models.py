from pydantic import BaseModel, Field
from typing import List, Dict, Any

class ModelInfoResponse(BaseModel):
    provider: str
    model: str
    status: str

class GroundedQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Question to ask the grounded model")

class GroundedQueryResponse(BaseModel):
    query: str
    answer: str
    retrieved_chunks: List[Dict[str, Any]]
    model_used: str
    latency_ms: float
