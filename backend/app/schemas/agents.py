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


# Bounded general agent task flow (Planner) -- separate from the fixed
# four-agent investigation pipeline above.
class AgentTaskStepOut(BaseModel):
    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[Any] = None
    observation_status: Optional[str] = None
    is_final: bool = False

class AgentRunTaskRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="Natural-language task for the agent to accomplish using its tools")
    workspace_id: Optional[str] = Field(
        None,
        description="Isolated file/execution workspace identifier. Defaults to a freshly generated id if omitted.",
    )
    max_steps: Optional[int] = Field(None, ge=1, le=20, description="Override the default bounded step limit (server-enforced maximum applies).")

class AgentRunTaskResponse(BaseModel):
    goal: str
    workspace_id: str
    steps: List[AgentTaskStepOut]
    final_answer: Optional[str] = None
    stopped_reason: str
    step_count: int
    total_ms: float
