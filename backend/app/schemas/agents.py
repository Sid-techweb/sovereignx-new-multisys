from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Phase 7, Stage 2 Schemas
class AgentInvestigateRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Question/query to investigate")
    context_id: Optional[str] = Field(None, description="Correlation context ID for tracking tool executions")

class AgentInvestigateResponse(BaseModel):
    query: str
    answer: str
    retrieved_chunks: List[Dict[str, Any]]
    confidence: float
    tool_executions: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    requires_human_review: bool = False
    escalation_reason: Optional[str] = None

# Phase 1/2 Placeholder Schemas
class AgentRunRequest(BaseModel):
    agent_id: str = Field(..., description="The ID of the target agent")
    task: str = Field(..., description="The task description for the agent")

class AgentRunResponse(BaseModel):
    agent_id: str
    status: str
    result: str
