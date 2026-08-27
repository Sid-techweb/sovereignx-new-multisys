import logging
from fastapi import APIRouter, HTTPException, Depends
from app.config import settings
from app.gateway import get_gateway, ModelGateway
from app.gateway.exceptions import (
    UnsupportedProviderError,
    OllamaUnavailableError,
    ProviderInitializationError,
    ProviderExecutionError
)
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import ModelInfoResponse, ChatRequest, ChatResponse, AnalysisRequest, GroundedQueryRequest, GroundedQueryResponse
from app.services.grounding import build_grounding_prompt

logger = logging.getLogger("sovereignx")
router = APIRouter()

@router.get("/models", response_model=ModelInfoResponse)
async def get_models():
    """
    Returns the currently configured model provider and model information.
    """
    provider = settings.MODEL_PROVIDER
    model = settings.MODEL_NAME if provider.lower() != "mock" else "mock-document-analyzer"
    
    # Determine the status of the model provider
    status = "available"
    if provider.lower() == "ollama":
        import httpx
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(settings.OLLAMA_BASE_URL)
                if res.status_code != 200:
                    status = "offline"
        except Exception:
            status = "offline"
            
    return ModelInfoResponse(
        provider=provider,
        model=model,
        status=status
    )

@router.post("/models/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, gateway: ModelGateway = Depends(get_gateway)):
    """
    Sends the prompt to the configured Model Gateway and returns the analysis.
    Uses dependency injection so routes do not depend directly on concrete gateways.
    """
    try:
        logger.info("Analysis request received via /models/chat")
        analysis_req = AnalysisRequest(input_text=request.prompt)
        response = await gateway.analyze(analysis_req)
        return ChatResponse(
            finding=response.finding,
            sop_reference=response.sop_reference,
            confidence=response.confidence,
            recommended_action=response.recommended_action
        )
    except (UnsupportedProviderError, OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError):
        # Let custom gateway exceptions bubble up to global exception handlers
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /models/chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/models/grounded-query", response_model=GroundedQueryResponse)
async def grounded_query(
    request: GroundedQueryRequest,
    db: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_gateway)
):
    """
    Retrieves evidence from the RAG knowledge base for the query, constructs a
    highly-structured grounding prompt, and calls the configured Model Gateway
    to generate an answer with citations.
    """
    import time
    from app.rag.embeddings import BGEM3EmbeddingProvider
    from app.rag.retriever import KnowledgeBaseRetriever
    from app.rag.exceptions import SearchQueryError, EmbeddingModelUnavailableError, DatabaseConnectionError

    query = request.query
    logger.info(f"Received grounded-query request: '{query}'")

    # 1. Retrieve relevant evidence chunks from the RAG pipeline
    try:
        embedder = BGEM3EmbeddingProvider()
        retriever = KnowledgeBaseRetriever(db, embedder)
        results, below_threshold = retriever.retrieve(query, top_k=5)
    except (SearchQueryError, EmbeddingModelUnavailableError, DatabaseConnectionError) as e:
        logger.error(f"Retrieval failure during grounded-query: {e}")
        raise HTTPException(status_code=503, detail=f"RAG retrieval failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during retrieval: {e}")
        raise HTTPException(status_code=500, detail=f"Internal retrieval error: {str(e)}")

    # 2. Build the grounding prompt via shared helper
    system_prompt, full_prompt = build_grounding_prompt(query, results)

    # Print the literal prompt string sent to Qwen2.5-7B-Instruct
    print("\n--- LITERAL PROMPT SENT TO OLLAMA START ---")
    print(f"SYSTEM PROMPT:\n{system_prompt}\n")
    print(f"USER PROMPT:\n{full_prompt}")
    print("--- LITERAL PROMPT SENT TO OLLAMA END ---\n")

    # 3. Call the configured Model Gateway
    start_time = time.perf_counter()
    try:
        answer = await gateway.generate(prompt=full_prompt, system_prompt=system_prompt)
    except (UnsupportedProviderError, OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError):
        # Bubble up gateway-specific exceptions
        raise
    except Exception as e:
        logger.error(f"Error calling model gateway: {e}")
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {str(e)}")
    end_time = time.perf_counter()
    
    latency_ms = (end_time - start_time) * 1000.0

    return GroundedQueryResponse(
        query=query,
        answer=answer,
        retrieved_chunks=results,
        model_used=settings.MODEL_NAME if settings.MODEL_PROVIDER.lower() != "mock" else "mock-document-analyzer",
        latency_ms=round(latency_ms, 2)
    )

