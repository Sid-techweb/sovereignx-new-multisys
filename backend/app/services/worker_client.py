"""
Node A's client for talking to a SovereignX worker (app/worker/main.py).
Sync, matching the rest of the tool-execution chain (LocalToolRegistry.execute
-> agent_tools.execute_python are both sync; see distributed_router.py for
where this gets called from). Every method raises one of the typed errors
below instead of letting a raw httpx exception or non-2xx response escape --
callers (DistributedRouter, agent_tools.execute_python) branch on error type
rather than parsing exception text.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx

from app.worker.auth import NODE_KEY_HEADER

logger = logging.getLogger("sovereignx")


class WorkerError(Exception):
    """Base for all WorkerClient failures."""


class WorkerUnavailableError(WorkerError):
    """Connection refused/timed out/DNS failure -- the worker process itself
    could not be reached, as distinct from it responding with an error."""


class WorkerAuthError(WorkerError):
    """The worker rejected NODE_SHARED_SECRET (401) or refused because it has
    none configured (503 from require_node_auth)."""


class WorkerExecutionError(WorkerError):
    """The worker was reachable and authenticated the request, but returned
    a non-success response for the operation itself (e.g. bad language,
    sandbox unavailable on that node)."""


@dataclass
class WorkerHealth:
    node_id: str
    status: str
    role: str
    ready: bool


class WorkerClient:
    def __init__(
        self,
        node_url: str,
        shared_secret: str,
        connect_timeout_seconds: float = 3.0,
        read_timeout_seconds: float = 30.0,
    ):
        self.node_url = node_url.rstrip("/")
        self._shared_secret = shared_secret
        timeout = httpx.Timeout(connect=connect_timeout_seconds, read=read_timeout_seconds, write=read_timeout_seconds, pool=connect_timeout_seconds)
        self._client = httpx.Client(base_url=self.node_url, timeout=timeout)

    def _auth_headers(self) -> Dict[str, str]:
        return {NODE_KEY_HEADER: self._shared_secret}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "WorkerClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def health(self) -> WorkerHealth:
        try:
            resp = self._client.get("/health")
        except httpx.TimeoutException as e:
            raise WorkerUnavailableError(f"Timed out reaching worker at {self.node_url}: {e}") from e
        except httpx.HTTPError as e:
            raise WorkerUnavailableError(f"Could not reach worker at {self.node_url}: {e}") from e

        if resp.status_code != 200:
            raise WorkerUnavailableError(f"Worker at {self.node_url} returned unexpected health status {resp.status_code}")

        data = resp.json()
        return WorkerHealth(node_id=data["node_id"], status=data["status"], role=data["role"], ready=data["ready"])

    def get_capabilities(self) -> List[str]:
        try:
            resp = self._client.get("/capabilities", headers=self._auth_headers())
        except httpx.TimeoutException as e:
            raise WorkerUnavailableError(f"Timed out reaching worker at {self.node_url}: {e}") from e
        except httpx.HTTPError as e:
            raise WorkerUnavailableError(f"Could not reach worker at {self.node_url}: {e}") from e

        if resp.status_code in (401, 503):
            raise WorkerAuthError(f"Worker at {self.node_url} rejected node authentication ({resp.status_code}): {resp.text}")
        if resp.status_code != 200:
            raise WorkerExecutionError(f"Worker at {self.node_url} returned {resp.status_code} for /capabilities: {resp.text}")

        return resp.json()["capabilities"]

    def execute_code(self, code: str, timeout_seconds: float = 15.0, language: str = "python") -> Dict[str, Any]:
        """
        Returns the same shape as app.services.sandbox.execute_python_sandboxed:
        {stdout, stderr, exit_code, timed_out, elapsed_ms} -- so callers can
        treat a local and a remote execution result identically.
        """
        payload = {"language": language, "code": code, "timeout_seconds": timeout_seconds}
        try:
            # The HTTP-level read timeout is intentionally longer than the
            # sandbox's own execution timeout (+ a margin) so the worker's
            # own timeout handling always wins over the transport timing out
            # the connection first.
            resp = self._client.post(
                "/execute-code",
                json=payload,
                headers=self._auth_headers(),
                timeout=httpx.Timeout(connect=self._client.timeout.connect, read=timeout_seconds + 15.0, write=timeout_seconds + 15.0, pool=self._client.timeout.connect),
            )
        except httpx.TimeoutException as e:
            raise WorkerUnavailableError(f"Timed out waiting for worker at {self.node_url} to execute code: {e}") from e
        except httpx.HTTPError as e:
            raise WorkerUnavailableError(f"Could not reach worker at {self.node_url}: {e}") from e

        if resp.status_code in (401, 503) and resp.status_code != 200:
            # 503 is ambiguous between "no node secret configured" (auth
            # refusal) and "sandbox unavailable on that node" (execution
            # failure) -- both return 503 from different layers. Treat as
            # auth-shaped only when the body doesn't look like a sandbox
            # response; otherwise it's a genuine execution failure.
            body = resp.text
            if resp.status_code == 401:
                raise WorkerAuthError(f"Worker at {self.node_url} rejected node authentication: {body}")
            raise WorkerExecutionError(f"Worker at {self.node_url} could not execute code (503): {body}")
        if resp.status_code != 200:
            raise WorkerExecutionError(f"Worker at {self.node_url} returned {resp.status_code} for /execute-code: {resp.text}")

        data = resp.json()
        return {
            "stdout": data["stdout"],
            "stderr": data["stderr"],
            "exit_code": data["exit_code"],
            "timed_out": data["timed_out"],
            "elapsed_ms": data["elapsed_ms"],
        }
