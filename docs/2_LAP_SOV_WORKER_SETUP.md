# 2 Lap Sov — Worker (Node B) Setup

This document is for whoever configures the **second laptop** as a SovereignX
worker node ("Node B"). It only covers running the worker service — nothing
here touches Node A (SovereignX Core), which keeps running exactly as it does
today.

Node B does **not** need: the frontend, chat history, the document database,
pgvector, or the four-agent investigation pipeline. It only accepts
authenticated code-execution requests from Node A and runs them in the same
Docker sandbox Node A uses locally.

---

## 1. Required branch/commit

Check out the same repository, on the branch that has the Phase 2 worker
service:

```bash
git fetch origin
git checkout feature/multi-node-sovereignx
```

Confirm the worker files exist:

```bash
ls backend/app/worker/main.py backend/app/services/sandbox.py
```

## 2. Requirements

- **Python** — the same version as Node A's backend `.venv` (3.10+).
- **Docker Desktop** (or Docker Engine) — required. The worker refuses to
  execute code if Docker isn't reachable (`SandboxUnavailableError` -> a
  clean 503, not a crash).
- **Ollama** — **not required** on Node B for this phase. The worker does
  not run any model; it only executes sandboxed Python. (A future phase may
  add model-inference capability to a worker — out of scope here.)

Install Python dependencies (same `requirements.txt` as Node A's backend):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Verify Docker is reachable:

```bash
docker info
```

## 3. NODE_SHARED_SECRET setup

The worker and Node A authenticate each other with one pre-shared secret,
sent as the `X-Sovereign-Node-Key` header. **Do not commit this value
anywhere.** Generate one locally, e.g.:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set it as an environment variable (or in a local, gitignored `.env`) on
**both** Node A and Node B — it must be the identical string on both sides:

```
NODE_SHARED_SECRET=<the generated value>
```

If `NODE_SHARED_SECRET` is empty on the worker, it refuses **every**
execution/capabilities request with `503` — an unset secret never means
"open to anyone."

## 4. Worker's own configuration (on Node B)

Set these environment variables (or `.env` values) on Node B before starting
the worker:

```
NODE_ID=node-b
NODE_SHARED_SECRET=<the same secret as above>
```

`NODE_ID` is only used in the worker's own `/health` response and its logs —
pick any short, unique identifier per worker.

## 5. Start the worker

From `backend/`, with the venv activated:

```bash
uvicorn app.worker.main:app --host 127.0.0.1 --port 9001
```

**Binds to `127.0.0.1` only for the local-validation phase.** Do not bind
`0.0.0.0` yet (see §9 below) — that's a deliberate later step, not the
default.

## 6. Node A's configuration (on Node A, to talk to this worker)

On Node A, set:

```
SOVEREIGN_DISTRIBUTED_MODE=true
NODE_SHARED_SECRET=<the same secret as Node B>
AI_NODES_CONFIG=[{"node_id": "node-b", "url": "http://127.0.0.1:9001", "role": "worker", "capabilities": ["SANDBOX_EXECUTION"]}]
```

`AI_NODES_CONFIG` is a JSON array — one object per worker node. `url` is the
**only** thing that changes when this becomes a real second machine (see §9).

## 7. Health test

With the worker running, from Node A (or any machine that can reach
`127.0.0.1:9001` — i.e. Node B itself during local validation):

```bash
curl http://127.0.0.1:9001/health
```

Expected:

```json
{"node_id": "node-b", "status": "healthy", "role": "worker", "ready": true}
```

`/health` is intentionally unauthenticated — it reveals no secrets, matching
Node A's own `GET /health` convention.

## 8. Capabilities test

```bash
curl -H "X-Sovereign-Node-Key: <the shared secret>" http://127.0.0.1:9001/capabilities
```

Expected:

```json
{"node_id": "node-b", "capabilities": ["SANDBOX_EXECUTION"]}
```

If you get `401`, the header is missing or the secret doesn't match. If you
get `503`, the worker's own `NODE_SHARED_SECRET` isn't set.

## 9. execute-code test

```bash
curl -X POST http://127.0.0.1:9001/execute-code \
  -H "X-Sovereign-Node-Key: <the shared secret>" \
  -H "Content-Type: application/json" \
  -d '{"language": "python", "code": "print(1+1)", "timeout_seconds": 10}'
```

Expected:

```json
{"success": true, "exit_code": 0, "stdout": "2\n", "stderr": "", "timed_out": false, "elapsed_ms": <number>}
```

Only `"language": "python"` is accepted — `shell`/`bash`/`cmd`/`powershell`/
anything else is rejected with `422`. This is a code-execution surface, not
a remote shell.

## 10. Firewall / private-LAN guidance (for the REAL second laptop, later)

This phase only validates Node A and Node B as two processes on
`127.0.0.1` on the **same** machine. Moving to a real second laptop later
requires **no code change** — only:

1. On Node B, bind to the machine's actual private-LAN interface instead of
   `127.0.0.1` (e.g. `--host 192.168.x.x`, the laptop's real private IP —
   never `0.0.0.0` without a firewall rule restricting the port to the LAN).
2. On Node A, update `AI_NODES_CONFIG`'s `url` for `node-b` to
   `http://<NODE_B_PRIVATE_LAN_IP>:9001`.
3. Ensure the two laptops are on the same trusted private network, and that
   Node B's OS firewall allows inbound TCP on port 9001 **only from Node A's
   IP**, not the whole LAN.
4. Never forward this port through a router/NAT to the public internet, and
   never use ngrok/cloudflared/any tunnel for it — this project's sovereignty
   model requires the worker to stay unreachable from outside the trusted
   private network.

An address that merely *looks* like a private-LAN IP is not automatically
trusted by SovereignX Core — only a node explicitly present in
`AI_NODES_CONFIG` is ever contacted or classified as `PRIVATE_LAN` in the
audit trail (see `app/services/node_registry.py::classify_node_scope`).

## 11. Offline / runtime requirement

The worker makes **no outbound network calls of its own** beyond what Node A
sends it — it doesn't call Ollama, doesn't call any cloud API, and the
sandboxed code it runs has `--network none` (no network access at all, even
to Node B's own LAN). The only network surface is the inbound HTTP API
itself, authenticated by `NODE_SHARED_SECRET`.

## 12. Known limitation carried over from Node A

Qwen2-VL (vision/OCR) is **not** part of this worker and is not planned for
it in this phase — that capability has a known native-crash risk under
investigation on Node A itself (see the project's P1 backlog: "Qwen2-VL
process isolation"). Do not add vision capability to a worker before that is
resolved.
