import re
from enum import Enum
from typing import Optional

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}


class ChatRoute(str, Enum):
    """
    The four capabilities the chat router can select between. RAG is one
    capability among several, not the chatbot itself -- GENERAL_CHAT is the
    default whenever the message does not clearly require document grounding.
    """
    GENERAL_CHAT = "GENERAL_CHAT"
    DOCUMENT_RAG = "DOCUMENT_RAG"
    MULTIMODAL = "MULTIMODAL"
    EXISTING_TOOL_FLOW = "EXISTING_TOOL_FLOW"


# Deterministic, offline phrase patterns that indicate the user is explicitly
# scoping their question to an uploaded/referenced document. Kept intentionally
# conservative: the presence of *some* document in the knowledge base must
# never, by itself, force RAG (see routing test matrix row: "What is an LSTM?"
# while a PDF happens to be uploaded -> GENERAL_CHAT).
_DOCUMENT_SCOPED_PATTERNS = [
    r"according to (?:this|the) (?:document|report|manual|pdf|file|upload)",
    r"from the uploaded (?:document|pdf|file|report|manual)",
    r"in the uploaded (?:document|pdf|file|report|manual)",
    r"summarize (?:this|the uploaded) (?:document|pdf|file|report|manual)",
    r"summarize what (?:was|is) uploaded",
    r"what does (?:this|the) (?:document|report|manual|pdf|file) say",
    r"based on (?:this|the) (?:document|pdf|file|report|manual)(?: i (?:uploaded|attached))?",
    r"based on the (?:uploaded|attached) (?:document|pdf|file|report|manual)",
    r"the (?:document|pdf|report|manual|file) says",
    r"per the (?:document|report|manual|pdf|file)",
    r"as per the (?:document|report|manual|pdf|file)",
    r"in (?:this|the) (?:document|report|manual|pdf)\b",
    r"according to (?:my|our) (?:document|report|manual|pdf|upload)",
    r"compare (?:the |its )?(?:document|report|pdf|manual)('s)? recommendation",
]

_DOCUMENT_SCOPED_REGEX = re.compile("|".join(_DOCUMENT_SCOPED_PATTERNS), re.IGNORECASE)


def is_document_scoped_message(message: str) -> bool:
    """Deterministic keyword/pattern check -- no external classifier is used."""
    if not message:
        return False
    return bool(_DOCUMENT_SCOPED_REGEX.search(message))


def classify_route(
    message: str,
    attached_document_id: Optional[str] = None,
    attached_document_file_type: Optional[str] = None,
) -> ChatRoute:
    """
    Selects GENERAL_CHAT, DOCUMENT_RAG, or MULTIMODAL for a chat turn.

    Rules (deterministic, no external/cloud classifier):
    1. A document explicitly attached to *this* turn always grounds the
       answer -- an image attachment routes to MULTIMODAL, any other
       supported document type routes to DOCUMENT_RAG.
    2. Otherwise, explicit document-referencing phrasing in the message
       (e.g. "according to this document", "summarize the uploaded PDF")
       routes to DOCUMENT_RAG against the whole knowledge base.
    3. Everything else defaults to GENERAL_CHAT. Documents merely existing
       in the knowledge base does NOT force RAG.
    """
    if attached_document_id:
        if attached_document_file_type and attached_document_file_type.lower() in IMAGE_EXTENSIONS:
            return ChatRoute.MULTIMODAL
        return ChatRoute.DOCUMENT_RAG

    if is_document_scoped_message(message):
        return ChatRoute.DOCUMENT_RAG

    return ChatRoute.GENERAL_CHAT
