import ctypes
import sys
import logging
from dataclasses import dataclass
from typing import Optional
from app.config import settings

logger = logging.getLogger("sovereignx")


@dataclass
class MemoryStatus:
    """
    Snapshot of system memory pressure, used as a preflight signal before
    invoking BGE-M3.

    `commit_headroom_mb` (Windows: CommitLimit - CommittedBytes) is the
    signal that was proven -- via controlled A/B testing with an isolated,
    independently-versioned ML runtime stack -- to predict BGE-M3 native
    crashes on this class of machine. Free physical RAM alone was proven
    MISLEADING: the machine showed several GB "free" while still crashing,
    because it was near its virtual-memory commit limit rather than out of
    physical RAM. This is a PREVENTION signal only, not a guarantee -- see
    module docstring below.
    """
    available_physical_mb: float
    committed_mb: float
    commit_limit_mb: float
    commit_headroom_mb: float
    safe_for_embedding: bool
    threshold_mb: float
    source: str  # "windows_commit_charge" | "fallback_available_ram"


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("sullAvailExtendedVirtual", ctypes.c_uint64),
    ]


def _query_windows_memory() -> Optional[_MEMORYSTATUSEX]:
    """
    Calls the Win32 GlobalMemoryStatusEx API directly via ctypes -- a fast
    (sub-millisecond), in-process, native call. Deliberately NOT implemented
    by shelling out to PowerShell/Get-Counter per request: that approach
    (used during investigation) takes hundreds of milliseconds per call,
    which is too slow for a per-request preflight check.

    ullTotalPageFile / ullAvailPageFile are the same commit-limit /
    available-commit metrics validated against `Get-Counter '\\Memory\\Commit
    Limit'` and `'\\Memory\\Committed Bytes'` during the investigation.
    """
    if sys.platform != "win32":
        return None
    stat = _MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    except Exception as e:
        logger.warning(f"GlobalMemoryStatusEx call failed: {e}")
        return None
    if not ok:
        return None
    return stat


def get_memory_status(threshold_mb: Optional[float] = None) -> MemoryStatus:
    """
    Returns the current memory-pressure snapshot used to decide whether it
    is safe to invoke a native embedding model right now.

    `threshold_mb` defaults to BGE_MIN_COMMIT_HEADROOM_MB (the historically
    validated BGE-M3 margin) when omitted, so every existing BGE call site
    is unaffected. Pass a different threshold for a provider with a
    different measured footprint (e.g. E5_MIN_COMMIT_HEADROOM_MB when
    E5_USE_ISOLATED_WORKER=True) -- see model_resource_manager.py.

    IMPORTANT: this is a PREVENTION mechanism, not a guarantee. Resource
    availability can change between this check and the actual embedding
    call (another process can allocate memory in between), and a native
    fault cannot be caught or predicted with certainty from Python. The
    actual crash-containment guarantee comes from running the model in an
    isolated worker process (see embedding_worker_manager.py), not from
    this preflight check.
    """
    threshold_mb = threshold_mb if threshold_mb is not None else settings.BGE_MIN_COMMIT_HEADROOM_MB
    stat = _query_windows_memory()

    if stat is None:
        # Non-Windows fallback: coarser signal, available RAM only. This
        # deployment target is Windows; this branch exists so the helper
        # degrades gracefully rather than failing outright elsewhere.
        try:
            import psutil
            vm = psutil.virtual_memory()
            available_mb = vm.available / (1024 * 1024)
        except Exception as e:
            logger.warning(f"Fallback memory check failed: {e}")
            available_mb = 0.0
        return MemoryStatus(
            available_physical_mb=available_mb,
            committed_mb=0.0,
            commit_limit_mb=0.0,
            commit_headroom_mb=available_mb,
            safe_for_embedding=available_mb >= threshold_mb,
            threshold_mb=threshold_mb,
            source="fallback_available_ram",
        )

    available_physical_mb = stat.ullAvailPhys / (1024 * 1024)
    commit_limit_mb = stat.ullTotalPageFile / (1024 * 1024)
    commit_headroom_mb = stat.ullAvailPageFile / (1024 * 1024)
    committed_mb = commit_limit_mb - commit_headroom_mb

    return MemoryStatus(
        available_physical_mb=available_physical_mb,
        committed_mb=committed_mb,
        commit_limit_mb=commit_limit_mb,
        commit_headroom_mb=commit_headroom_mb,
        safe_for_embedding=commit_headroom_mb >= threshold_mb,
        threshold_mb=threshold_mb,
        source="windows_commit_charge",
    )
