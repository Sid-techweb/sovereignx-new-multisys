from typing import List, Optional

from pydantic import BaseModel, Field

# Only "python" is accepted -- see execute-code's language allowlist in
# main.py. A worker is a code-EXECUTION surface, not a general remote-shell;
# widening this list is a deliberate, reviewed decision, not a config knob.
SUPPORTED_LANGUAGES = {"python"}

MAX_CODE_BYTES = 64 * 1024  # generous for a generated script, far below anything pathological
MAX_TIMEOUT_SECONDS = 60.0


class HealthResponse(BaseModel):
    node_id: str
    status: str  # "healthy" | "degraded"
    role: str
    ready: bool


class CapabilitiesResponse(BaseModel):
    node_id: str
    capabilities: List[str]


class ExecuteCodeRequest(BaseModel):
    language: str = Field(..., description="Must be one of the worker's supported languages (currently: python only).")
    code: str = Field(..., min_length=1, max_length=MAX_CODE_BYTES)
    timeout_seconds: Optional[float] = Field(default=15.0, gt=0, le=MAX_TIMEOUT_SECONDS)


class ExecuteCodeResponse(BaseModel):
    success: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_ms: float
