import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session

from app.config import settings
from app.gateway.base import ModelGateway
from app.gateway.exceptions import OllamaUnavailableError, ProviderExecutionError, ProviderInitializationError
from app.chat.models import ChatConversation, ChatMessage
from app.chat.routing import ChatRoute, classify_route
from app.chat.prompts import (
    get_general_chat_system_prompt,
    DOCUMENT_RAG_CHAT_SYSTEM_PROMPT,
    MULTIMODAL_CHAT_SYSTEM_PROMPT,
    build_rag_context_block,
    build_multimodal_context_block,
)
from app.rag.embeddings import BGEM3EmbeddingProvider
from app.rag.retriever import KnowledgeBaseRetriever
from app.rag.exceptions import SearchQueryError, EmbeddingModelUnavailableError, DatabaseConnectionError
from app.services.metadata_store import DocumentMetadataStore
from app.services.storage import LocalDocumentStorage
from app.services import get_extractor, ExtractionError
from app.services.model_resource_manager import get_resource_manager
from app.schemas.documents import ExtractedDocument
from app.agents.agents import extract_temperature_metrics, extract_vibration_metrics
from app.services.tools import LocalToolRegistry

logger = logging.getLogger("sovereignx")

MODEL_UNAVAILABLE_MESSAGE = "Local language model is currently unavailable. Please check that Ollama is running."


class ChatServiceError(Exception):
    """
    Raised for chat-turn failures that need a specific, user-facing category
    rather than a generic 500 -- callers map `category` to the right HTTP
    status and message (see app/api/chat.py).
    """
    def __init__(self, message: str, category: str):
        super().__init__(message)
        self.category = category  # "model_unavailable" | "document_failure"


@dataclass
class PreparedTurn:
    """Everything needed to call the model gateway for one chat turn, plus
    the per-stage timings measured while assembling it. Shared by both the
    non-streaming and streaming orchestration paths so routing/retrieval/
    prompt-construction logic is not duplicated between them."""
    convo: ChatConversation
    route: ChatRoute
    messages: List[Dict[str, str]]
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    tool_executions: List[Dict[str, Any]] = field(default_factory=list)
    rag_degraded_reason: Optional[str] = None
    timings: Dict[str, float] = field(default_factory=dict)


def get_or_create_conversation(db: Session, conversation_id: Optional[str] = None) -> ChatConversation:
    if conversation_id:
        convo = db.query(ChatConversation).filter(
            ChatConversation.conversation_id == conversation_id
        ).first()
        if convo:
            return convo
    convo = ChatConversation()
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo


def _load_recent_history(db: Session, conversation_id: str, max_messages: int) -> List[ChatMessage]:
    """Most recent N messages, returned in chronological order."""
    if max_messages <= 0:
        return []
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(max_messages)
        .all()
    )
    return list(reversed(rows))


def _trim_history_to_char_budget(history: List[ChatMessage], max_chars: int) -> List[ChatMessage]:
    """Keeps the most recent messages that fit within CHAT_CONTEXT_MAX_CHARS, dropping oldest first."""
    if max_chars <= 0:
        return []
    kept: List[ChatMessage] = []
    total = 0
    for msg in reversed(history):
        length = len(msg.content or "")
        if total + length > max_chars and kept:
            break
        kept.append(msg)
        total += length
    return list(reversed(kept))


def _persist_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    route: Optional[str] = None,
    document_id: Optional[str] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
) -> ChatMessage:
    msg = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        route=route,
        document_id=document_id,
        sources=json.dumps(sources) if sources else None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _maybe_set_conversation_title(db: Session, convo: ChatConversation, user_message: str) -> None:
    if convo.title:
        return
    title = user_message.strip().replace("\n", " ")
    convo.title = (title[:57] + "...") if len(title) > 60 else title
    db.add(convo)
    db.commit()


def _run_deterministic_tools(retrieved_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reuses the existing Phase 6 deterministic tool-comparison logic
    (temperature/vibration vs. SOP limit) against retrieved RAG evidence,
    exactly as the existing AnalysisAgent does for /agents/investigate.
    """
    registry = LocalToolRegistry()
    executions = []

    temp_metrics = extract_temperature_metrics(retrieved_chunks)
    if temp_metrics:
        resp = registry.execute(
            tool_name="compare_reading_against_sop_limit",
            arguments={
                "reading_value": temp_metrics["reading"],
                "limit_value": temp_metrics["limit"],
                "comparison_type": "greater_than",
                "unit": "C"
            },
            context_id=None
        )
        executions.append(resp.model_dump())

    vib_metrics = extract_vibration_metrics(retrieved_chunks)
    if vib_metrics:
        resp = registry.execute(
            tool_name="compare_reading_against_sop_limit",
            arguments={
                "reading_value": vib_metrics["reading"],
                "limit_value": vib_metrics["limit"],
                "comparison_type": "greater_than",
                "unit": "mm/s"
            },
            context_id=None
        )
        executions.append(resp.model_dump())

    return executions


def _ensure_document_extracted(document_id: str) -> ExtractedDocument:
    """
    Returns the extracted content for a document, running extraction inline
    (reusing the same extractor factory as POST /documents/{id}/process) if
    it has not been processed yet. Raises ChatServiceError on failure.
    """
    meta_store = DocumentMetadataStore(settings.DOCUMENT_STORAGE_PATH)
    storage = LocalDocumentStorage(settings.DOCUMENT_STORAGE_PATH)

    meta = meta_store.get(document_id)
    if not meta:
        raise ChatServiceError(f"Attached document {document_id} was not found.", "document_failure")

    try:
        return storage.get_extracted_document(document_id)
    except FileNotFoundError:
        pass  # not processed yet -- extract inline below

    ext = f".{meta['file_type']}"
    storage_name = f"{document_id}{ext}"
    if not storage.exists(storage_name):
        raise ChatServiceError(f"Attached document {document_id} file content is missing.", "document_failure")

    try:
        content = storage.get(storage_name)
        extractor = get_extractor(ext)
        extracted_text, extra_meta = extractor.extract(content, filename=meta["filename"])
        extracted_doc = ExtractedDocument(
            document_id=document_id,
            filename=meta["filename"],
            source=meta["source"],
            content=extracted_text,
            content_type="text",
            extraction_status="processed" if extracted_text else "processed_with_no_text",
            metadata={**extra_meta, "mime_type": meta["mime_type"]},
            created_at=meta["uploaded_at"],
        )
        extracted_dir = storage.base_path / "extracted"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        with open(extracted_dir / f"{document_id}.json", "w", encoding="utf-8") as f:
            f.write(extracted_doc.model_dump_json())
        meta["status"] = extracted_doc.extraction_status
        meta_store.save(document_id, meta)
        return extracted_doc
    except ExtractionError as e:
        raise ChatServiceError(f"Failed to process attached document: {str(e)}", "document_failure") from e


def _prepare_turn(
    db: Session,
    conversation_id: Optional[str],
    user_message: str,
    attached_document_id: Optional[str] = None,
) -> PreparedTurn:
    """
    Routes the turn and assembles the exact message list to send to the
    model gateway (system prompt + history + optional RAG/multimodal
    context + current user message), with per-stage timings. Shared by the
    non-streaming and streaming call paths -- neither duplicates this logic.
    """
    timings: Dict[str, float] = {}
    convo = get_or_create_conversation(db, conversation_id)

    # 1. Routing (deterministic, local, no external classifier)
    t0 = time.perf_counter()
    attached_file_type = None
    if attached_document_id:
        meta_store = DocumentMetadataStore(settings.DOCUMENT_STORAGE_PATH)
        meta = meta_store.get(attached_document_id)
        if not meta:
            raise ChatServiceError(f"Attached document {attached_document_id} was not found.", "document_failure")
        attached_file_type = meta.get("file_type")

    route = classify_route(user_message, attached_document_id, attached_file_type)
    if route == ChatRoute.DOCUMENT_RAG and not settings.RAG_ENABLED:
        route = ChatRoute.GENERAL_CHAT
    timings["routing_ms"] = (time.perf_counter() - t0) * 1000.0

    # 2. History preparation
    t0 = time.perf_counter()
    history = _load_recent_history(db, convo.conversation_id, settings.CHAT_HISTORY_MAX_MESSAGES)
    history = _trim_history_to_char_budget(history, settings.CHAT_CONTEXT_MAX_CHARS)
    timings["history_ms"] = (time.perf_counter() - t0) * 1000.0

    retrieved_chunks: List[Dict[str, Any]] = []
    tool_executions: List[Dict[str, Any]] = []
    rag_degraded_reason: Optional[str] = None
    timings["retrieval_ms"] = 0.0

    # 3. Retrieval / document context (only for routes that need it)
    t0 = time.perf_counter()
    if route == ChatRoute.DOCUMENT_RAG:
        try:
            # Ensure the BGE worker is available before embedding -- lock-
            # coordinated against ModelResourceManager's Qwen-preemption
            # sequence so the two don't race (see model_resource_manager.py).
            get_resource_manager().ensure_embedding_available(timeout=settings.BGE_WORKER_STARTUP_TIMEOUT_SECONDS)
            embedder = BGEM3EmbeddingProvider()
            retriever = KnowledgeBaseRetriever(db, embedder)
            retrieved_chunks, _below_threshold = retriever.retrieve(user_message, top_k=5)
            if attached_document_id:
                retrieved_chunks = [
                    c for c in retrieved_chunks if c.get("document_id") == attached_document_id
                ] or retrieved_chunks
            tool_executions = _run_deterministic_tools(retrieved_chunks)
            if tool_executions:
                route = ChatRoute.EXISTING_TOOL_FLOW
        except (SearchQueryError, EmbeddingModelUnavailableError, DatabaseConnectionError) as e:
            # A RAG retrieval failure must not block general chat -- degrade gracefully.
            logger.warning(f"RAG retrieval failed, degrading to GENERAL_CHAT: {e}")
            rag_degraded_reason = str(e)
            route = ChatRoute.GENERAL_CHAT
    timings["retrieval_ms"] = (time.perf_counter() - t0) * 1000.0

    extracted_image_text = None
    extracted_image_filename = None
    if route == ChatRoute.MULTIMODAL and attached_document_id:
        t0 = time.perf_counter()
        extracted_doc = _ensure_document_extracted(attached_document_id)
        extracted_image_text = extracted_doc.content
        extracted_image_filename = extracted_doc.filename
        timings["retrieval_ms"] += (time.perf_counter() - t0) * 1000.0

    # 4. Prompt / context assembly
    t0 = time.perf_counter()
    if route in (ChatRoute.DOCUMENT_RAG, ChatRoute.EXISTING_TOOL_FLOW):
        system_prompt = DOCUMENT_RAG_CHAT_SYSTEM_PROMPT
        context_block = build_rag_context_block(retrieved_chunks)
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "system", "content": f"Relevant evidence from local documents:\n\n{context_block}"})
        messages.append({"role": "user", "content": user_message})
    elif route == ChatRoute.MULTIMODAL:
        system_prompt = MULTIMODAL_CHAT_SYSTEM_PROMPT
        context_block = build_multimodal_context_block(extracted_image_text, extracted_image_filename)
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "system", "content": context_block})
        messages.append({"role": "user", "content": user_message})
    else:
        system_prompt = get_general_chat_system_prompt(settings.CHAT_SYSTEM_PROMPT)
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": user_message})
    timings["prompt_ms"] = (time.perf_counter() - t0) * 1000.0

    return PreparedTurn(
        convo=convo,
        route=route,
        messages=messages,
        retrieved_chunks=retrieved_chunks,
        tool_executions=tool_executions,
        rag_degraded_reason=rag_degraded_reason,
        timings=timings,
    )


async def handle_chat_turn(
    db: Session,
    gateway: ModelGateway,
    conversation_id: Optional[str],
    user_message: str,
    attached_document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Core non-streaming chat orchestration: routes the turn, assembles the
    right context, calls the local model gateway once, persists both sides
    of the turn, and returns a structured result including per-stage
    latency instrumentation.

    RAG is treated as one optional capability the router can select -- it is
    never a hard requirement for answering a general question.
    """
    total_start = time.perf_counter()
    prep = _prepare_turn(db, conversation_id, user_message, attached_document_id)

    # Make room for Qwen if needed (stops the BGE worker only if it's
    # actually resident, not already busy, and commit headroom is
    # currently insufficient -- see ModelResourceManager for the measured
    # evidence behind this). Never raises; best-effort preparation only.
    resource_info = get_resource_manager().ensure_llm_capacity()

    # Model inference (single call, shared across all routes)
    t0 = time.perf_counter()
    try:
        answer = await gateway.chat_completion(prep.messages)
    except (OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError) as e:
        raise ChatServiceError(MODEL_UNAVAILABLE_MESSAGE, "model_unavailable") from e
    model_ms = (time.perf_counter() - t0) * 1000.0

    # Persistence
    _maybe_set_conversation_title(db, prep.convo, user_message)
    _persist_message(db, prep.convo.conversation_id, "user", user_message, document_id=attached_document_id)
    assistant_msg = _persist_message(
        db, prep.convo.conversation_id, "assistant", answer,
        route=prep.route.value, sources=prep.retrieved_chunks or None
    )

    timings = {
        **prep.timings,
        "resource_wait_ms": resource_info["resource_wait_ms"],
        "model_ms": model_ms,
        "total_ms": (time.perf_counter() - total_start) * 1000.0,
    }
    timings = {k: round(v, 2) for k, v in timings.items()}

    logger.info(
        f"chat_turn conversation_id={prep.convo.conversation_id} route={prep.route.value} "
        f"routing_ms={timings['routing_ms']} history_ms={timings['history_ms']} "
        f"retrieval_ms={timings['retrieval_ms']} prompt_ms={timings['prompt_ms']} "
        f"resource_wait_ms={timings['resource_wait_ms']} "
        f"model_ms={timings['model_ms']} total_ms={timings['total_ms']}"
    )

    return {
        "conversation_id": prep.convo.conversation_id,
        "message_id": assistant_msg.message_id,
        "route": prep.route.value,
        "answer": answer,
        "retrieved_chunks": prep.retrieved_chunks,
        "tool_executions": prep.tool_executions,
        "rag_degraded_reason": prep.rag_degraded_reason,
        "timings": timings,
    }


async def stream_chat_turn(
    db: Session,
    gateway: ModelGateway,
    conversation_id: Optional[str],
    user_message: str,
    attached_document_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Streaming counterpart to handle_chat_turn(). Yields NDJSON-ready event
    dicts as the model generates tokens:

      {"type": "start", "conversation_id", "route", "retrieved_chunks", ...}
      {"type": "token", "content": "..."}                (repeated)
      {"type": "done", "message_id", "answer", "timings_ms", ...}
      {"type": "error", "category", "message", "partial_content"}

    Every exception is caught and turned into an "error" event instead of
    propagating: once the HTTP response has started streaming, raising here
    would just abort the connection with no clean signal to the client.

    The user message is persisted immediately (so it survives even if
    generation fails before any tokens arrive). Exactly ONE assistant
    message is persisted, after the full response has been accumulated --
    never one row per token/chunk. If generation fails partway through,
    whatever was accumulated so far is persisted as that single message
    rather than being discarded.
    """
    total_start = time.perf_counter()

    try:
        prep = _prepare_turn(db, conversation_id, user_message, attached_document_id)
    except ChatServiceError as e:
        yield {"type": "error", "category": e.category, "message": str(e)}
        return
    except Exception as e:
        logger.error(f"Unexpected error preparing streamed chat turn: {e}")
        yield {"type": "error", "category": "internal", "message": "Failed to prepare chat request."}
        return

    _maybe_set_conversation_title(db, prep.convo, user_message)
    _persist_message(db, prep.convo.conversation_id, "user", user_message, document_id=attached_document_id)

    yield {
        "type": "start",
        "conversation_id": prep.convo.conversation_id,
        "route": prep.route.value,
        "retrieved_chunks": prep.retrieved_chunks,
        "tool_executions": prep.tool_executions,
        "rag_degraded_reason": prep.rag_degraded_reason,
    }

    # Make room for Qwen if needed -- see handle_chat_turn's comment and
    # ModelResourceManager for the measured evidence. Never raises.
    resource_info = get_resource_manager().ensure_llm_capacity()

    accumulated: List[str] = []
    ttft_ms: Optional[float] = None
    ollama_metadata: Dict[str, Any] = {}
    model_start = time.perf_counter()

    try:
        async for chunk in gateway.stream_chat_completion(prep.messages):
            if chunk.content:
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - model_start) * 1000.0
                accumulated.append(chunk.content)
                yield {"type": "token", "content": chunk.content}
            if chunk.done:
                ollama_metadata = chunk.metadata or {}
    except (OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError):
        full_text = "".join(accumulated)
        if full_text:
            _persist_message(
                db, prep.convo.conversation_id, "assistant", full_text,
                route=prep.route.value, sources=prep.retrieved_chunks or None
            )
        logger.warning(
            f"chat_turn_stream conversation_id={prep.convo.conversation_id} "
            f"failed after {len(accumulated)} chunk(s); partial content "
            f"{'persisted' if full_text else 'not persisted (empty)'}"
        )
        yield {
            "type": "error",
            "category": "model_unavailable",
            "message": MODEL_UNAVAILABLE_MESSAGE,
            "partial_content": full_text,
        }
        return
    except Exception as e:
        full_text = "".join(accumulated)
        if full_text:
            _persist_message(
                db, prep.convo.conversation_id, "assistant", full_text,
                route=prep.route.value, sources=prep.retrieved_chunks or None
            )
        logger.error(f"Unexpected error during streamed generation: {e}")
        yield {
            "type": "error",
            "category": "internal",
            "message": "Chat generation failed unexpectedly.",
            "partial_content": full_text,
        }
        return

    model_ms = (time.perf_counter() - model_start) * 1000.0
    full_text = "".join(accumulated)

    assistant_msg = _persist_message(
        db, prep.convo.conversation_id, "assistant", full_text,
        route=prep.route.value, sources=prep.retrieved_chunks or None
    )

    timings = {
        **prep.timings,
        "resource_wait_ms": resource_info["resource_wait_ms"],
        "ttft_ms": ttft_ms,
        "model_ms": model_ms,
        "total_ms": (time.perf_counter() - total_start) * 1000.0,
    }
    timings = {k: (round(v, 2) if v is not None else None) for k, v in timings.items()}

    logger.info(
        f"chat_turn_stream conversation_id={prep.convo.conversation_id} route={prep.route.value} "
        f"routing_ms={timings['routing_ms']} history_ms={timings['history_ms']} "
        f"retrieval_ms={timings['retrieval_ms']} prompt_ms={timings['prompt_ms']} "
        f"resource_wait_ms={timings['resource_wait_ms']} "
        f"ttft_ms={timings['ttft_ms']} model_ms={timings['model_ms']} total_ms={timings['total_ms']} "
        f"eval_count={ollama_metadata.get('eval_count')} "
        f"eval_duration_ms={ollama_metadata.get('eval_duration_ms')} "
        f"load_duration_ms={ollama_metadata.get('load_duration_ms')}"
    )

    yield {
        "type": "done",
        "message_id": assistant_msg.message_id,
        "conversation_id": prep.convo.conversation_id,
        "route": prep.route.value,
        "answer": full_text,
        "retrieved_chunks": prep.retrieved_chunks,
        "tool_executions": prep.tool_executions,
        "rag_degraded_reason": prep.rag_degraded_reason,
        "timings_ms": timings,
        "ollama_metadata": ollama_metadata,
    }
