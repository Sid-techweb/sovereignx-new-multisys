from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class ParameterDefinition(BaseModel):
    type: str = Field(..., description="Data type of the parameter (e.g. float, str, list[float])")
    description: str = Field(..., description="Description of the parameter")
    required: bool = Field(True, description="Whether the parameter is required")
    default: Optional[Any] = Field(None, description="Default value if not provided")
    options: Optional[List[Any]] = Field(None, description="Optional list of allowed values")

class ToolDefinition(BaseModel):
    name: str = Field(..., description="Unique programmatic name of the tool")
    description: str = Field(..., description="Helpful description of what the tool does")
    parameters: Dict[str, ParameterDefinition] = Field(..., description="Parameters required by this tool")

class ToolExecutionRequest(BaseModel):
    tool_name: str = Field(..., description="The name of the tool to execute")
    arguments: Dict[str, Any] = Field(..., description="Key-value arguments for the tool")
    context_id: Optional[str] = Field(None, description="Optional correlation context ID (e.g. investigation or query ID)")

class ToolExecutionResponse(BaseModel):
    tool_name: str = Field(..., description="The name of the tool that was executed")
    outputs: Dict[str, Any] = Field(..., description="Structured return values from the tool")
    status: str = Field(..., description="Execution status: 'success' or 'failed'")
    error: Optional[str] = Field(None, description="Error message if execution failed")
    execution_log_id: str = Field(..., description="UUID representing this execution record")
    duration_ms: float = Field(..., description="Time taken to execute in milliseconds")
    context_id: Optional[str] = Field(None, description="Optional correlation context ID")

class ToolExecutionLogEntry(BaseModel):
    id: str = Field(..., description="Unique execution log entry ID")
    timestamp: str = Field(..., description="ISO timestamp of when the execution started")
    tool_name: str = Field(..., description="Name of the executed tool")
    inputs: Dict[str, Any] = Field(..., description="Input arguments passed to the tool")
    outputs: Optional[Dict[str, Any]] = Field(None, description="Result outputs of the tool")
    status: str = Field(..., description="Status: 'success' or 'failed'")
    error: Optional[str] = Field(None, description="Error details if failed")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")
    context_id: Optional[str] = Field(None, description="Optional correlation context ID")
