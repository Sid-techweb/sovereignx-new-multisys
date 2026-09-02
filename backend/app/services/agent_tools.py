"""
File and code-execution tools for the agent (Planner) -- the MRPL/SIH26117
problem statement's "read/write files" and "execute code safely in a
sandbox" requirements. Deliberately separate from app/services/tools.py's
original deterministic engineering-calculation tools (compare_reading_
against_sop_limit etc.) -- different trust model: those operate on numbers
the caller supplies, these touch a real (if constrained) filesystem and
spawn real (if sandboxed) processes.

Every file tool is scoped to a `workspace_id` (typically the conversation_id
or an agent task_id) -- there is no host-filesystem access, no arbitrary
absolute path, and no reaching outside app/services/agent_workspace/<id>/.
This mirrors the path-traversal protection pattern already used elsewhere
in this codebase (e.g. api/reports.py's download_report): resolve, then
require is_relative_to() the workspace root.
"""
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings
from app.services.execution_audit import log_execution_event
from app.services.node_registry import LOCAL_NODE_ID
from app.services.sandbox import execute_python_sandboxed, SandboxUnavailableError

logger = logging.getLogger("sovereignx")

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2MB per file -- generous for reports/CSV/code, not for dumping arbitrary data
MAX_WORKSPACE_FILES = 200
_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def _workspace_root() -> Path:
    base = Path(settings.DOCUMENT_STORAGE_PATH).resolve().parent
    root = (base / "agent_workspace").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_workspace_dir(workspace_id: str) -> Path:
    if not _WORKSPACE_ID_RE.match(workspace_id or ""):
        raise ValueError(
            "workspace_id must be 1-100 characters of letters, digits, '-', or '_' only."
        )
    root = _workspace_root()
    ws_dir = (root / workspace_id).resolve()
    if not ws_dir.is_relative_to(root):
        raise ValueError("Invalid workspace_id.")
    ws_dir.mkdir(parents=True, exist_ok=True)
    return ws_dir


def _resolve_file_path(workspace_id: str, relative_path: str) -> Path:
    if not relative_path or relative_path.strip() == "":
        raise ValueError("path must not be empty.")
    ws_dir = _resolve_workspace_dir(workspace_id)
    # Reject absolute paths outright before resolving -- is_relative_to() is
    # the real guarantee, but this gives a clearer error message for the
    # common "agent passes an absolute path" mistake.
    if Path(relative_path).is_absolute():
        raise ValueError("path must be relative to the workspace -- absolute paths are not allowed.")
    target = (ws_dir / relative_path).resolve()
    if not target.is_relative_to(ws_dir):
        raise ValueError("path escapes the workspace directory -- not allowed.")
    return target


def read_file(workspace_id: str, path: str) -> Dict[str, Any]:
    target = _resolve_file_path(workspace_id, path)
    if not target.exists() or not target.is_file():
        raise ValueError(f"File not found in workspace: {path}")
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"File too large to read ({size} bytes, limit {MAX_FILE_BYTES}).")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError("File is not valid UTF-8 text -- binary files are not supported by read_file.")
    return {"path": path, "content": content, "size_bytes": size}


def write_file(workspace_id: str, path: str, content: str) -> Dict[str, Any]:
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(f"Content too large to write (limit {MAX_FILE_BYTES} bytes).")
    ws_dir = _resolve_workspace_dir(workspace_id)
    existing = list(ws_dir.rglob("*"))
    target = _resolve_file_path(workspace_id, path)
    if not target.exists() and len([p for p in existing if p.is_file()]) >= MAX_WORKSPACE_FILES:
        raise ValueError(f"Workspace file limit reached ({MAX_WORKSPACE_FILES} files).")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    size = target.stat().st_size
    logger.info(f"agent_tool write_file workspace={workspace_id} path={path} size_bytes={size}")
    return {"path": path, "size_bytes": size}


def list_files(workspace_id: str) -> Dict[str, Any]:
    ws_dir = _resolve_workspace_dir(workspace_id)
    files: List[Dict[str, Any]] = []
    for p in sorted(ws_dir.rglob("*")):
        if p.is_file():
            files.append({
                "path": str(p.relative_to(ws_dir)).replace("\\", "/"),
                "size_bytes": p.stat().st_size,
            })
    return {"workspace_id": workspace_id, "files": files, "count": len(files)}


def _execute_python_local(code: str, timeout_seconds: float) -> Dict[str, Any]:
    """
    Runs `code` inside this process's own Docker-isolated sandbox (see
    app/services/sandbox.py) -- network disabled, memory/CPU/pids capped,
    read-only root filesystem, non-root user, bounded timeout, throwaway
    working directory removed after execution. Raises (surfaced as a clean
    tool failure, not a crash) if Docker itself isn't reachable; a program
    that runs but exits non-zero or raises inside the sandbox is NOT an
    error at this layer -- that's a normal result the caller/agent
    evaluates (stdout/stderr/exit_code).
    """
    try:
        return execute_python_sandboxed(code, timeout_seconds=timeout_seconds)
    except SandboxUnavailableError as e:
        raise ValueError(str(e)) from e


def execute_python(code: str, timeout_seconds: float = 15.0) -> Dict[str, Any]:
    """
    The Planner's single entry point for sandboxed code execution -- it
    calls this tool by name only and never knows or decides whether
    execution happens on this machine or a remote worker node. That
    decision lives entirely here and in distributed_router.py:

      SOVEREIGN_DISTRIBUTED_MODE=false (the default): calls
      _execute_python_local() directly, with ZERO node-registry lookups,
      ZERO health checks, and ZERO network calls beyond the sandbox itself
      -- this branch is checked first and returns before anything
      distributed-related is even imported into the call path.

      SOVEREIGN_DISTRIBUTED_MODE=true: asks DistributedRouter for a
      target. A healthy configured worker executes remotely over HTTP
      (app/services/worker_client.py); if no worker is healthy, this
      explicitly falls back to the local sandbox (is_fallback=True in both
      the returned "execution" block and the audit log -- never silently
      presented as if the remote node had succeeded).

    Returns the original {stdout, stderr, exit_code, timed_out, elapsed_ms}
    shape unchanged (elapsed_ms is always the sandbox's own measured
    execution time, local or remote) plus two additive blocks:
    "execution" (where it ran) and "metrics" (timing breakdown -- see
    Phase 2's latency instrumentation requirement).
    """
    t_total0 = time.perf_counter()

    if not settings.SOVEREIGN_DISTRIBUTED_MODE:
        result = _execute_python_local(code, timeout_seconds)
        total_ms = round((time.perf_counter() - t_total0) * 1000.0, 2)
        result["execution"] = {
            "scope": "LOCAL",
            "node_id": LOCAL_NODE_ID,
            "execution_scope": "LOCAL",
            "is_fallback": False,
        }
        result["metrics"] = {
            "capability_selection_ms": 0.0,
            "node_selection_ms": 0.0,
            "node_health_ms": 0.0,
            "network_rtt_ms": 0.0,
            "remote_execution_ms": 0.0,
            "sandbox_ms": result["elapsed_ms"],
            "total_tool_ms": total_ms,
        }
        log_execution_event(
            capability="SANDBOX_EXECUTION", tool="execute_python", selected_node=LOCAL_NODE_ID,
            execution_scope="LOCAL", remote=False, success=(result["exit_code"] == 0 and not result["timed_out"]),
            latency_ms=total_ms,
        )
        return result

    from app.services.distributed_router import distributed_router, CapabilityUnavailableError

    try:
        decision = distributed_router.route_sandbox_execution()
    except CapabilityUnavailableError as e:
        raise ValueError(str(e)) from e

    if decision.scope == "LOCAL":
        result = _execute_python_local(code, timeout_seconds)
        total_ms = round((time.perf_counter() - t_total0) * 1000.0, 2)
        result["execution"] = {
            "scope": "LOCAL", "node_id": LOCAL_NODE_ID, "execution_scope": "LOCAL", "is_fallback": decision.is_fallback,
        }
        result["metrics"] = {
            "capability_selection_ms": 0.0,
            "node_selection_ms": decision.selection_ms,
            "node_health_ms": decision.health_ms,
            "network_rtt_ms": 0.0,
            "remote_execution_ms": 0.0,
            "sandbox_ms": result["elapsed_ms"],
            "total_tool_ms": total_ms,
        }
        log_execution_event(
            capability="SANDBOX_EXECUTION", tool="execute_python", selected_node=LOCAL_NODE_ID,
            execution_scope="LOCAL", remote=False, success=(result["exit_code"] == 0 and not result["timed_out"]),
            latency_ms=total_ms, is_fallback=decision.is_fallback, extra={"reason": decision.reason},
        )
        return result

    # REMOTE
    from app.services.worker_client import WorkerClient, WorkerError
    from app.services.node_health_cache import node_health_cache
    from app.services.model_registry import HealthState
    from app.services.node_registry import node_registry

    t_remote0 = time.perf_counter()
    try:
        with WorkerClient(
            decision.node_url, settings.NODE_SHARED_SECRET,
            connect_timeout_seconds=settings.WORKER_CONNECT_TIMEOUT_SECONDS,
            read_timeout_seconds=settings.WORKER_READ_TIMEOUT_SECONDS,
        ) as client:
            result = client.execute_code(code, timeout_seconds=timeout_seconds)
    except WorkerError as e:
        # The worker looked healthy at selection time but failed to actually
        # execute -- invalidate its cached health so the NEXT call re-probes
        # rather than trusting a result that just proved wrong, then fall
        # back to local for THIS call rather than failing the whole task.
        node_health_cache.invalidate(decision.node_id)
        node_registry.set_health(decision.node_id, HealthState.OFFLINE)
        logger.warning(f"agent_tool execute_python: remote execution on '{decision.node_id}' failed ({e}); falling back to local sandbox.")
        result = _execute_python_local(code, timeout_seconds)
        total_ms = round((time.perf_counter() - t_total0) * 1000.0, 2)
        result["execution"] = {
            "scope": "LOCAL", "node_id": LOCAL_NODE_ID, "execution_scope": "LOCAL", "is_fallback": True,
        }
        result["metrics"] = {
            "capability_selection_ms": 0.0,
            "node_selection_ms": decision.selection_ms,
            "node_health_ms": decision.health_ms,
            "network_rtt_ms": 0.0,
            "remote_execution_ms": round((time.perf_counter() - t_remote0) * 1000.0, 2),
            "sandbox_ms": result["elapsed_ms"],
            "total_tool_ms": total_ms,
        }
        log_execution_event(
            capability="SANDBOX_EXECUTION", tool="execute_python", selected_node=LOCAL_NODE_ID,
            execution_scope="LOCAL", remote=False, success=(result["exit_code"] == 0 and not result["timed_out"]),
            latency_ms=total_ms, is_fallback=True, extra={"reason": f"remote execution failed: {e}"},
        )
        return result

    remote_ms = round((time.perf_counter() - t_remote0) * 1000.0, 2)
    total_ms = round((time.perf_counter() - t_total0) * 1000.0, 2)
    sandbox_ms = result["elapsed_ms"]
    network_rtt_ms = round(max(0.0, remote_ms - sandbox_ms), 2)
    result["execution"] = {
        "scope": "REMOTE", "node_id": decision.node_id, "execution_scope": decision.execution_scope,
        "is_fallback": decision.is_fallback,
    }
    result["metrics"] = {
        "capability_selection_ms": 0.0,
        "node_selection_ms": decision.selection_ms,
        "node_health_ms": decision.health_ms,
        "network_rtt_ms": network_rtt_ms,
        "remote_execution_ms": remote_ms,
        "sandbox_ms": sandbox_ms,
        "total_tool_ms": total_ms,
    }
    log_execution_event(
        capability="SANDBOX_EXECUTION", tool="execute_python", selected_node=decision.node_id,
        execution_scope=decision.execution_scope, remote=True,
        success=(result["exit_code"] == 0 and not result["timed_out"]),
        latency_ms=total_ms, is_fallback=decision.is_fallback, extra={"reason": decision.reason},
    )
    return result
