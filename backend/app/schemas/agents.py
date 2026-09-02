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


# Bounded multi-step agentic task (planner loop -- see app/agents/planner.py)
class AgentTaskRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="The task/goal for the agent to accomplish using local tools.")
    workspace_id: Optional[str] = Field(
        None,
        description="Task workspace identifier scoping file tool access (e.g. a conversation id). "
                     "A fresh UUID is generated if omitted.",
    )
    max_steps: Optional[int] = Field(None, ge=1, le=20, description="Override the default step bound (server-capped at 20).")

class AgentStepView(BaseModel):
    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[Any] = None
    observation_status: Optional[str] = None
    is_final: bool = False

class AgentTaskResponse(BaseModel):
    goal: str
    workspace_id: str
    final_answer: Optional[str]
    stopped_reason: str
    steps: List[AgentStepView]
    total_ms: float
    workspace_files: List[Dict[str, Any]] = Field(default_factory=list)
