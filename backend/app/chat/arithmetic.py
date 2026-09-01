"""
Deterministic-arithmetic detection for chat routing.

Benchmark finding this exists to address: qwen3.5:4b can enter a long,
non-terminating self-verification loop on plain multi-digit arithmetic
(e.g. "10384 x 827") even with a larger token budget and an explicit
concise-output instruction -- see model_resource_manager.py-adjacent
benchmark notes. The fix is architectural, not model-specific: obvious
arithmetic should never depend on an LLM doing the math freehand, for ANY
model, since even a fast/correct model pays needless latency re-deriving
something a calculator gets right instantly.

This module does NOT implement its own arithmetic evaluator -- it only
detects that a message is a calculation request and normalizes the natural-
language phrasing into a plain symbolic expression string. The actual
computation is delegated to the EXISTING safe AST evaluator in
app/tools/calculation_verifier.py (evaluate_expression / verify_calculation),
reused as-is, not duplicated.

Deliberately conservative: a message must contain an actual, evaluatable
numeric expression to be classified as arithmetic. A message that merely
mentions numbers or math vocabulary ("Explain calculus", "How are
multiplication and exponentiation different?") will fail extraction/
evaluation and correctly fall through to GENERAL_CHAT -- see
test_chat_routing.py for the false-positive guard tests.
"""
import re
from typing import Optional

# A comma is only treated as part of the number itself when it's a proper
# thousands grouping (comma immediately followed by exactly 3 digits) --
# NOT when it's a list separator with a following space, e.g. the comma in
# "Add 120, 450 and 991" must stay a separator, not get absorbed into "120,".
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"

# Longest-phrase-first so "multiplied by" is tried before a hypothetical
# shorter overlapping alternative.
_WORD_OPERATORS = [
    (re.compile(r"\bmultiplied\s+by\b", re.IGNORECASE), "*"),
    (re.compile(r"\btimes\b", re.IGNORECASE), "*"),
    (re.compile(r"\bdivided\s+by\b", re.IGNORECASE), "/"),
    (re.compile(r"\bplus\b", re.IGNORECASE), "+"),
    (re.compile(r"\bminus\b", re.IGNORECASE), "-"),
]

_PERCENT_OF_RE = re.compile(rf"({_NUM})\s*(?:%|percent)\s*of\s*({_NUM})", re.IGNORECASE)
_ADD_LIST_RE = re.compile(
    rf"\badd\s+({_NUM}(?:\s*,\s*{_NUM})*(?:\s*,?\s*and\s+{_NUM})?)", re.IGNORECASE
)

# A trigger requires actual calculation intent -- either an imperative verb,
# a percent-of phrase, an add-list, or an explicit operator (symbolic or
# word) directly between two numbers. Bare numbers alone never trigger this.
_TRIGGER_RE = re.compile(
    rf"\bcalculate\b|\bcompute\b|{_PERCENT_OF_RE.pattern}|{_ADD_LIST_RE.pattern}"
    rf"|({_NUM})\s*(?:[\+\-\*/]|x|×|\^)\s*({_NUM})"
    rf"|({_NUM})\s+(?:times|multiplied\s+by|divided\s+by|plus|minus)\s+({_NUM})",
    re.IGNORECASE,
)

# What remains after normalization must look like a pure arithmetic
# expression -- digits, whitespace, and math symbols only, no letters.
_PURE_EXPRESSION_RE = re.compile(r"^[\d\s\.\+\-\*/%\(\)]+$")


def _normalize_candidate(text: str) -> str:
    text = text.strip()
    for pattern, symbol in _WORD_OPERATORS:
        text = pattern.sub(f" {symbol} ", text)
    text = re.sub(r"(\d)\s*[x×]\s*(\d)", r"\1 * \2", text)
    text = text.replace(",", "")
    return text.strip()


def extract_arithmetic_expression(message: str) -> Optional[str]:
    """
    Best-effort extraction of a plain symbolic arithmetic expression from a
    natural-language calculation request. Returns None (never guesses) if
    no confident, evaluatable expression is found -- callers must treat
    None as "not an arithmetic request", not as an error.
    """
    if not message:
        return None

    add_match = _ADD_LIST_RE.search(message)
    if add_match:
        terms = re.split(r"\s*,\s*and\s+|\s*,\s*|\s+and\s+", add_match.group(1).strip())
        terms = [t.replace(",", "").strip() for t in terms if t.strip()]
        if len(terms) >= 2:
            candidate = " + ".join(terms)
            return candidate if _PURE_EXPRESSION_RE.match(candidate) else None

    percent_match = _PERCENT_OF_RE.search(message)
    if percent_match:
        n, m = percent_match.group(1).replace(",", ""), percent_match.group(2).replace(",", "")
        return f"({n} / 100) * {m}"

    # Explicit parenthesized expression, e.g. "(25 * 8) + 17" -- pass the
    # whole balanced-paren-onward span through the normalizer as-is.
    paren_match = re.search(r"\([^()]*\)[^?.!]*", message)
    if paren_match and re.search(r"[\+\-\*/]", paren_match.group(0)):
        candidate = _normalize_candidate(paren_match.group(0))
        if _PURE_EXPRESSION_RE.match(candidate):
            return candidate

    # General "A <op> B" span, symbolic or word-form operator.
    normalized_full = _normalize_candidate(message)
    binary_match = re.search(rf"({_NUM})\s*([\+\-\*/])\s*({_NUM})", normalized_full)
    if binary_match:
        candidate = binary_match.group(0)
        if _PURE_EXPRESSION_RE.match(candidate):
            return candidate

    return None


def is_arithmetic_request(message: str) -> bool:
    """Deterministic, offline check -- no external/LLM classifier."""
    if not message or not _TRIGGER_RE.search(message):
        return False
    return extract_arithmetic_expression(message) is not None
