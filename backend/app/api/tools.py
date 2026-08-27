import logging
from typing import List
from fastapi import APIRouter, HTTPException, Query
from app.schemas.tools import ToolDefinition, ToolExecutionRequest, ToolExecutionResponse, ToolExecutionLogEntry
from app.services.tools import tool_registry

logger = logging.getLogger("sovereignx")
router = APIRouter(prefix="/tools", tags=["Tools"])

@router.get("", response_model=List[ToolDefinition])
async def list_tools():
    """
    Returns a list of all registered tools and their input parameters/types.
    """
    try:
        return tool_registry.list_tools()
    except Exception as e:
        logger.error(f"Failed to list tools: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tools list.")

@router.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(request: ToolExecutionRequest):
    """
    Executes a specific tool using the provided arguments, logs the execution, 
    and returns a structured output response.
    """
    try:
        logger.info(f"Executing tool '{request.tool_name}' with arguments: {request.arguments} (context: {request.context_id})")
        response = tool_registry.execute(request.tool_name, request.arguments, context_id=request.context_id)
        if response.status == "failed":
            logger.warning(f"Tool '{request.tool_name}' execution failed: {response.error}")
        else:
            logger.info(f"Tool '{request.tool_name}' executed successfully in {response.duration_ms}ms")
        return response
    except Exception as e:
        logger.error(f"Unexpected error executing tool '{request.tool_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs", response_model=List[ToolExecutionLogEntry])
async def get_tool_logs(limit: int = Query(50, ge=1, le=100)):
    """
    Retrieves the execution logs for tools executed in the system.
    """
    try:
        return tool_registry.get_logs(limit=limit)
    except Exception as e:
        logger.error(f"Failed to retrieve tool logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve execution logs.")
