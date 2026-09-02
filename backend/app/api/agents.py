import logging
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.gateway import get_gateway, ModelGateway
from app.gateway.exceptions import (
    UnsupportedProviderError,
    OllamaUnavailableError,
    ProviderInitializationError,
    ProviderExecutionError
)
from app.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    AgentInvestigateRequest,
    AgentInvestigateResponse,
    AgentTaskRequest,
    AgentTaskResponse,
    AgentStepView,
    AnalysisRequest
)
from app.agents import IntakeAgent, RAGAgent, AnalysisAgent, ReportAgent
from app.agents.planner import run_agent_task, MAX_AGENT_STEPS
from app.services.tools import LocalToolRegistry
from app.services.agent_tools import list_files as list_workspace_files

logger = logging.getLogger("sovereignx")
router = APIRouter()

@router.post("/agents/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest, gateway: ModelGateway = Depends(get_gateway)):
    """
    Placeholder endpoint demonstrating how an agent query is routed through
    the ModelGateway. Does not execute full agent/RAG workflows yet.
    """
    try:
        logger.info(f"Agent task received: {request.task}")
        # Build agent specific prompt and call ModelGateway
        agent_prompt = f"Agent Role Task: {request.task}"
        analysis_req = AnalysisRequest(input_text=agent_prompt)
        analysis = await gateway.analyze(analysis_req)
        
        result_summary = (
            f"Placeholder execution completed. Analysis outcome: "
            f"Finding='{analysis.finding}', "
            f"Action='{analysis.recommended_action}'"
        )
        
        return AgentRunResponse(
            agent_id=request.agent_id,
            status="completed",
            result=result_summary
        )
    except (UnsupportedProviderError, OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /agents/run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/investigate", response_model=AgentInvestigateResponse)
async def investigate(
    request: AgentInvestigateRequest,
    db: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_gateway)
):
    """
    Stage 2 endpoint: Routes the query through a four-agent workflow
    (IntakeAgent, RAGAgent, AnalysisAgent, and ReportAgent) with dynamic Phase 6 tool calling.
    """
    start_time = time.perf_counter()
    query = request.query
    context_id = request.context_id

    # 1. Document Intake Agent Checks Availability
    intake_agent = IntakeAgent()
    if not intake_agent.verify_evidence_availability(db):
        logger.warning("IntakeAgent: Knowledge base is empty (zero document chunks found in database).")
        raise HTTPException(
            status_code=400,
            detail="The knowledge base is completely empty. Please upload documents first."
        )

    try:
        # 2. RAG Agent Retrieves Relevant Chunks
        rag_agent = RAGAgent(db)
        retrieved_chunks = rag_agent.retrieve_evidence(query, top_k=5)

        # 3. Analysis Agent Performs LLM Grounding and Tool Execution
        analysis_agent = AnalysisAgent(gateway)
        analysis_result = await analysis_agent.analyze(
            query=query,
            retrieved_chunks=retrieved_chunks,
            context_id=context_id
        )

        # 4. Report Generation Agent structures final output
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        report_agent = ReportAgent()
        report = report_agent.format_report(
            query=query,
            answer=analysis_result["answer"],
            retrieved_chunks=retrieved_chunks,
            tool_executions=analysis_result["tool_executions"],
            model_used=gateway.model_name if hasattr(gateway, "model_name") else "mock-document-analyzer",
            latency_ms=duration_ms
        )

        confidence_val = float(report.get("confidence", 0.0))
        ESCALATION_THRESHOLD = 0.7000
        requires_human_review = confidence_val < ESCALATION_THRESHOLD
        escalation_reason = (
            f"Retrieval confidence ({confidence_val * 100:.1f}%) is below safety threshold ({ESCALATION_THRESHOLD * 100:.1f}%) — recommend manual verification before acting on this finding."
            if requires_human_review
            else None
        )

        return AgentInvestigateResponse(
            query=report["query"],
            answer=report["answer"],
            retrieved_chunks=report["retrieved_chunks"],
            confidence=report["confidence"],
            tool_executions=report["tool_executions"],
            metadata=report["metadata"],
            requires_human_review=requires_human_review,
            escalation_reason=escalation_reason
        )

    except (UnsupportedProviderError, OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError):
        # Bubble up gateway-specific exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /agents/investigate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/run-task", response_model=AgentTaskResponse)
async def run_task(request: AgentTaskRequest, gateway: ModelGateway = Depends(get_gateway)):
    """
    Bounded multi-step agentic task: the model plans, calls local tools
    (file I/O, sandboxed code execution, deterministic calculations, RAG
    knowledge search -- see LocalToolRegistry), observes results, and
    iterates until it reaches a Final Answer or the step limit. See
    app/agents/planner.py for the loop itself and its safety bounds.

    Distinct from /agents/investigate (a fixed retrieve-then-answer
    pipeline): this is a genuine agent loop that can take several tool
    actions in sequence to accomplish a goal, not just answer one question.
    """
    workspace_id = request.workspace_id or f"task-{uuid.uuid4().hex[:12]}"
    max_steps = min(request.max_steps, MAX_AGENT_STEPS * 2) if request.max_steps else MAX_AGENT_STEPS

    try:
        tool_registry = LocalToolRegistry()
        result = await run_agent_task(
            gateway=gateway,
            tool_registry=tool_registry,
            goal=request.goal,
            workspace_id=workspace_id,
            max_steps=max_steps,
        )

        try:
            files = list_workspace_files(workspace_id)["files"]
        except Exception:
            files = []

        return AgentTaskResponse(
            goal=result.goal,
            workspace_id=result.workspace_id,
            final_answer=result.final_answer,
            stopped_reason=result.stopped_reason,
            steps=[
                AgentStepView(
                    step_number=s.step_number,
                    thought=s.thought,
                    action=s.action,
                    action_input=s.action_input,
                    observation=s.observation,
                    observation_status=s.observation_status,
                    is_final=s.is_final,
                )
                for s in result.steps
            ],
            total_ms=result.total_ms,
            workspace_files=files,
        )
    except (UnsupportedProviderError, OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /agents/run-task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
