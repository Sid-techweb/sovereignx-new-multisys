"""
Sandboxed local code execution -- the project statement's explicit "a coding
task run and verified in a sandbox" requirement.

Isolation is Docker-based (Docker is already part of this stack -- see the
sovereignx-pgvector container), not a bare subprocess: subprocess-only
isolation cannot enforce real network/memory/CPU limits on Windows (no
cgroups, no `resource` module), so Docker gives the actual guarantees the
project asks for ("blocked network by default", "CPU/memory constraints
where practical") rather than a best-effort approximation of them.

Guarantees, all enforced by Docker/the container runtime, not just by
convention in this Python code:
  - network:  --network none            (container has no network stack at all)
  - memory:   --memory / --memory-swap  (hard cap, OOM-killed if exceeded)
  - cpu:      --cpus                    (hard cap)
  - pids:     --pids-limit              (fork-bomb containment)
  - fs:       --read-only + a single    (only one host directory is writable,
              read-write bind mount      a fresh, empty, throwaway temp dir;
              for the working directory) everything else in the container is
                                         read-only)
  - identity: --user nobody             (never runs as root inside the container)
  - timeout:  subprocess-level timeout on the `docker run` call itself, with
              an explicit `docker kill` fallback if the container outlives it
              (a killed `docker run` CLI process does not guarantee the
              container it launched also stops)
  - cleanup:  the host-side temp directory is a context manager -- removed
              whether execution succeeds, fails, or times out.

Runtime allowlist: Python only, deliberately (matches the project's "start
with Python if that fits existing architecture best" and keeps the surface
area small -- adding another language means auditing another image).
"""
import logging
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("sovereignx")

SANDBOX_IMAGE = "python:3.11-slim"
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_TIMEOUT_SECONDS = 60.0
MEMORY_LIMIT = "256m"
CPU_LIMIT = "1"
PIDS_LIMIT = "64"
MAX_OUTPUT_CHARS = 20000


class SandboxUnavailableError(Exception):
    """Docker itself isn't reachable -- distinct from the executed code failing."""
    pass


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5.0
        )
        return result.returncode == 0
    except Exception:
        return False


def execute_python_sandboxed(code: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, Any]:
    """
    Runs `code` as a standalone Python script inside an isolated, network-
    disabled, resource-capped container. Returns stdout/stderr/exit_code/
    timed_out/elapsed_ms -- never raises for code that fails or times out
    (that's a normal "failed" result the caller/agent should see and can act
    on), only for the sandbox infrastructure itself being unavailable.
    """
    timeout_seconds = min(max(timeout_seconds, 1.0), MAX_TIMEOUT_SECONDS)

    if not _docker_available():
        raise SandboxUnavailableError(
            "Sandboxed code execution is unavailable: Docker is not reachable. "
            "No code was executed."
        )

    container_name = f"sovereignx-sandbox-{uuid.uuid4().hex[:12]}"

    with tempfile.TemporaryDirectory(prefix="sovereignx_sandbox_") as tmpdir:
        script_path = Path(tmpdir) / "script.py"
        script_path.write_text(code, encoding="utf-8")

        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--network", "none",
            "--memory", MEMORY_LIMIT,
            "--memory-swap", MEMORY_LIMIT,
            "--cpus", CPU_LIMIT,
            "--pids-limit", PIDS_LIMIT,
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "-v", f"{tmpdir}:/workspace",
            "-w", "/workspace",
            "--user", "nobody",
            SANDBOX_IMAGE,
            "python", "-I", "/workspace/script.py",
        ]

        t0 = time.perf_counter()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_seconds + 5.0
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                f"sandbox_execution container={container_name} exit_code={result.returncode} "
                f"elapsed_ms={elapsed_ms:.1f}"
            )
            return {
                "stdout": result.stdout[:MAX_OUTPUT_CHARS],
                "stderr": result.stderr[:MAX_OUTPUT_CHARS],
                "exit_code": result.returncode,
                "timed_out": False,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        except subprocess.TimeoutExpired:
            # The docker CLI call timed out -- the container itself may still
            # be running (killing the CLI process does not stop it), so kill
            # it explicitly by name rather than assuming it's gone.
            try:
                subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=10.0)
            except Exception as e:
                logger.warning(f"sandbox_execution: failed to kill timed-out container {container_name}: {e}")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning(f"sandbox_execution container={container_name} TIMED OUT after {timeout_seconds}s")
            return {
                "stdout": "",
                "stderr": f"Execution exceeded the {timeout_seconds}s timeout and was terminated.",
                "exit_code": None,
                "timed_out": True,
                "elapsed_ms": round(elapsed_ms, 2),
            }
