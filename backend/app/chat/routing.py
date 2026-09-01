import re
from enum import Enum
from typing import Optional

from app.chat.arithmetic import is_arithmetic_request

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
#
# Built from a shared "document reference" grammar rather than one-off literal
# sentences, so natural variations (a determiner, an optional uploaded/attached
# modifier before OR after the noun, singular/plural) are handled uniformly --
# e.g. "according to the document" / "according to the uploaded document" /
# "according to this uploaded PDF" / "the document I uploaded" all reduce to
# the same underlying reference, instead of each needing its own pattern.
_DETERMINER = r"(?:this|that|the|my|our)"
_UPLOAD_MODIFIER = r"(?:uploaded|attached)"
# Nouns unambiguous enough to count as document-scoped even with no
# uploaded/attached modifier and no determiner-restriction concerns.
_DOC_NOUN_STRICT = r"(?:document|report|manual|pdf)s?\b"
# Nouns ("file", "upload") that are too generic on their own in a technical
# assistant's chat (e.g. "in the file", "from the file" could mean a code/log
# file, not a knowledge-base document) -- only trusted here when paired with
# an explicit uploaded/attached modifier, a determiner, or a low-ambiguity verb.
_DOC_NOUN_ANY = r"(?:document|report|manual|pdf|file|upload)s?\b"

# "the document", "the uploaded document", "this attached PDF", "my reports"
_REF_ANY = rf"{_DETERMINER}\s+(?:{_UPLOAD_MODIFIER}\s+)?{_DOC_NOUN_ANY}"
# "the document I uploaded", "the file I attached"
_REF_TRAILING = rf"{_DETERMINER}\s+{_DOC_NOUN_ANY}\s+i\s+(?:uploaded|attached)"
_REF = rf"(?:{_REF_ANY}|{_REF_TRAILING})"

# A stricter reference used for lower-precision trigger verbs ("from", "in",
# "using") where a bare "the file"/"the upload" is too likely to be a false
# positive: require either an explicit uploaded/attached modifier, or restrict
# the noun to the unambiguous set.
_REF_SAFE = rf"(?:{_DETERMINER}\s+{_UPLOAD_MODIFIER}\s+{_DOC_NOUN_ANY}|{_DETERMINER}\s+{_DOC_NOUN_STRICT})"
_REF_CONSERVATIVE = rf"(?:{_REF_SAFE}|{_REF_TRAILING})"

_DOCUMENT_SCOPED_PATTERNS = [
    rf"according to {_REF}",
    rf"as per {_REF}",
    rf"per {_REF}",
    rf"based on {_REF}",
    rf"what does {_REF} say",
    rf"summarize {_REF}",
    rf"{_REF} says",
    rf"from {_REF_CONSERVATIVE}",
    rf"in {_REF_CONSERVATIVE}",
    rf"using {_REF_CONSERVATIVE}",
    r"summarize what (?:was|is) uploaded",
    r"compare (?:the |its )?(?:document|report|pdf|manual)('s)? recommendation",
]

_DOCUMENT_SCOPED_REGEX = re.compile("|".join(_DOCUMENT_SCOPED_PATTERNS), re.IGNORECASE)


def is_document_scoped_message(message: str) -> bool:
    """Deterministic keyword/pattern check -- no external classifier is used."""
    if not message:
        return False
    return bool(_DOCUMENT_SCOPED_REGEX.search(message))


# Signals a deliberate pivot away from document-grounded continuation back
# to a general/conceptual question, even mid-conversation right after a
# DOCUMENT_RAG turn -- e.g. "Explain why temperature monitoring matters
# generally." Kept as a small, explicit, deterministic list rather than any
# kind of topic classifier.
_GENERAL_PIVOT_RE = re.compile(
    r"\bin general\b|\bgenerally\b|\bconceptually\b|\bas a concept\b|\bin theory\b",
    re.IGNORECASE,
)


def classify_route(
    message: str,
    attached_document_id: Optional[str] = None,
    attached_document_file_type: Optional[str] = None,
    previous_route: Optional["ChatRoute"] = None,
) -> ChatRoute:
    """
    Selects GENERAL_CHAT, DOCUMENT_RAG, MULTIMODAL, or EXISTING_TOOL_FLOW
    for a chat turn.

    Rules (deterministic, no external/cloud classifier):
    1. A document explicitly attached to *this* turn always grounds the
       answer -- an image attachment routes to MULTIMODAL, any other
       supported document type routes to DOCUMENT_RAG.
    2. Otherwise, explicit document-referencing phrasing in the message
       (e.g. "according to this document", "summarize the uploaded PDF")
       routes to DOCUMENT_RAG against the whole knowledge base. This is
       checked before the arithmetic check below, since "according to the
       document, what is 45 times the value listed?" means look the value
       up, not treat the numbers as already-known literals.
    3. Otherwise, an obvious deterministic arithmetic/calculation request
       (e.g. "what is 10384 times 827?") routes to EXISTING_TOOL_FLOW, so
       the numeric answer comes from the existing safe AST evaluator
       (app/tools/calculation_verifier.py) rather than free-text LLM math --
       see app/chat/arithmetic.py's module docstring for why (measured:
       even a fast/correct model can burn a large token budget re-deriving
       something a calculator gets right instantly, and can fail to
       terminate at all on some inputs).
    4. Otherwise, if the immediately preceding turn in *this* conversation
       was DOCUMENT_RAG/EXISTING_TOOL_FLOW, a natural short follow-up (e.g.
       "What is its vibration limit?", with no document phrase of its own)
       stays DOCUMENT_RAG too -- a real conversation about a document
       doesn't repeat "according to the document" every single turn. This
       "stickiness" breaks the moment the user signals a deliberate pivot to
       a general/conceptual question (see _GENERAL_PIVOT_RE) or the message
       is itself an arithmetic request (already routed above).
    5. Everything else defaults to GENERAL_CHAT. Documents merely existing
       in the knowledge base does NOT force RAG, and messages that merely
       mention numbers or math vocabulary ("Explain calculus", "How are
       multiplication and exponentiation different?") do NOT force the
       tool route -- see arithmetic.py's extraction guard.
    """
    if attached_document_id:
        if attached_document_file_type and attached_document_file_type.lower() in IMAGE_EXTENSIONS:
            return ChatRoute.MULTIMODAL
        return ChatRoute.DOCUMENT_RAG

    if is_document_scoped_message(message):
        return ChatRoute.DOCUMENT_RAG

    if is_arithmetic_request(message):
        return ChatRoute.EXISTING_TOOL_FLOW

    if previous_route in (ChatRoute.DOCUMENT_RAG, ChatRoute.EXISTING_TOOL_FLOW) and not _GENERAL_PIVOT_RE.search(message or ""):
        return ChatRoute.DOCUMENT_RAG

    return ChatRoute.GENERAL_CHAT
