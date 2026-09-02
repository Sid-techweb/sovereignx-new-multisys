"""
Structured audit logging for distributed tool execution -- proves, after
the fact, which node actually ran a given task rather than relying on a
Planner transcript alone. This is intentionally structured LOGGING only,
not a persisted database table: a `distributed_execution_audit` DB model
(SQLAlchemy + Alembic migration) is real follow-up scope, not implemented
here, so that claim is not overstated.

Never logs source code or file contents -- only the metadata needed to
answer "what ran, where, and did it succeed."
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

audit_logger = logging.getLogger("sovereignx.audit")


def log_execution_event(
    capability: str,
    tool: str,
    selected_node: str,
    execution_scope: str,
    remote: bool,
    success: bool,
    latency_ms: float,
    task_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    is_fallback: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capability": capability,
        "tool": tool,
        "selected_node": selected_node,
        "execution_scope": execution_scope,
        "remote": remote,
        "is_fallback": is_fallback,
        "success": success,
        "latency_ms": latency_ms,
        "task_id": task_id,
        "conversation_id": conversation_id,
    }
    if extra:
        record.update(extra)
    audit_logger.info(json.dumps(record, default=str))
