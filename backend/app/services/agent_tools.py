"""
File and code-execution tools for the agent (Planner) -- the project
statement's "read/write files" and "execute code safely in a sandbox"
requirements. Deliberately kept separate from app/services/tools.py's
original deterministic engineering-calculation tools (compare_reading_
against_sop_limit etc.) -- different trust model: those operate on numbers
the caller supplies, these touch a real (if constrained) filesystem and
spawn real (if sandboxed) processes, so they get their own path-safety and
size-limit review here rather than being buried alongside simple math.

Every file tool is scoped to a `workspace_id` (typically the conversation_id
or an agent task_id) -- there is no host-filesystem access, no arbitrary
absolute path, and no reaching outside app/services/agent_workspace/<id>/.
This mirrors the path-traversal protection pattern already used in
api/reports.py (download_report) and api/documents.py (get_document_content):
resolve, then require is_relative_to() the workspace root.
"""
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings
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
    # Reject absolute paths and any drive/UNC prefix outright before resolving --
    # is_relative_to() alone is the real guarantee, but this gives a clearer
    # error message for the common "agent passes an absolute path" mistake.
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


def execute_python(code: str, timeout_seconds: float = 15.0) -> Dict[str, Any]:
    """
    Runs `code` inside the Docker-isolated sandbox (see app/services/sandbox.py)
    -- network disabled, memory/CPU/pids capped, read-only root filesystem,
    non-root user, bounded timeout, throwaway working directory removed after
    execution. Raises (surfaced as a clean tool failure, not a crash) if
    Docker itself isn't reachable; a program that runs but exits non-zero or
    raises inside the sandbox is NOT an error at this layer -- that's a
    normal result the caller/agent evaluates (stdout/stderr/exit_code).
    """
    try:
        result = execute_python_sandboxed(code, timeout_seconds=timeout_seconds)
    except SandboxUnavailableError as e:
        raise ValueError(str(e)) from e
    return result
