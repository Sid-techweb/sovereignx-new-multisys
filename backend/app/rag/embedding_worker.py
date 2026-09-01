"""
Entry point for the isolated embedding worker process (BGE-M3 and,
optionally, E5 -- see provider argument below).

This module's `run_worker` function is the ONLY code path that ever
constructs `_BGEM3ModelRunner`/`_E5SmallModelRunner` for worker-isolated use
/ loads PyTorch+sentence-transformers in that role. It is invoked
exclusively inside a child process spawned by `EmbeddingWorkerManager` (see
embedding_worker_manager.py) via `multiprocessing.get_context("spawn")`. If
the model's native code SIGSEGVs here, only this child process dies -- the
parent FastAPI process is a separate OS process with a separate address
space and is unaffected.

Do not import torch/sentence-transformers anywhere else in the app at
module level for this reason: the whole point is that the main process
never has to touch that native stack directly (BGE-M3 always; E5 only when
E5_USE_ISOLATED_WORKER=True routes it through this same worker).
"""
import logging
import os
import time


def _build_runner(provider: str, model_name: str):
    if provider == "e5":
        from app.rag.embeddings import _E5SmallModelRunner
        return _E5SmallModelRunner(model_name)
    from app.rag.embeddings import _BGEM3ModelRunner
    return _BGEM3ModelRunner(model_name)


def run_worker(request_queue, response_queue, model_name: str, provider: str = "bge") -> None:
    """
    Runs forever (until a shutdown job or fatal init failure) inside the
    child process. Loads the configured model exactly once, then services
    embedding jobs from `request_queue`, replying on `response_queue`.

    Protocol:
      request:  {"request_id": str, "op": "embed", "texts": [str, ...]}
                {"op": "shutdown"}
      response: {"type": "ready", "pid": int}
                {"type": "init_failed", "pid": int, "error": str}
                {"request_id": str, "status": "ok", "vectors": [[float,...],...]}
                {"request_id": str, "status": "error", "error": str}

    Note: `texts` arriving here are already prefixed (query:/passage:) by
    the caller (E5SmallEmbeddingProvider.embed_query/embed_documents) when
    provider="e5" -- this worker calls the runner's raw get_embeddings(),
    it does not re-apply prefixing itself.
    """
    # Fresh process (spawned, not forked) -- needs its own logging config.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger(f"sovereignx.{provider}_worker")
    pid = os.getpid()
    logger.info(f"{provider} embedding worker starting, PID={pid}, model={model_name}")

    try:
        runner = _build_runner(provider, model_name)
        runner.initialize()
        logger.info(f"{provider} embedding worker (PID={pid}) model loaded successfully.")
    except Exception as e:
        logger.error(f"{provider} embedding worker (PID={pid}) failed to load model: {e}")
        response_queue.put({"type": "init_failed", "pid": pid, "error": str(e)})
        return

    response_queue.put({"type": "ready", "pid": pid})

    while True:
        job = request_queue.get()  # blocks until a job arrives
        if job is None or job.get("op") == "shutdown":
            logger.info(f"{provider} embedding worker (PID={pid}) received shutdown signal.")
            break

        request_id = job.get("request_id")
        texts = job.get("texts") or []
        t0 = time.perf_counter()
        try:
            vectors = runner.get_embeddings(texts)
            dt = (time.perf_counter() - t0) * 1000.0
            logger.info(f"{provider} embedding worker (PID={pid}) embedded {len(texts)} text(s) in {dt:.1f}ms")
            response_queue.put({"request_id": request_id, "status": "ok", "vectors": vectors})
        except Exception as e:
            logger.error(f"{provider} embedding worker (PID={pid}) encode failed: {e}")
            response_queue.put({"request_id": request_id, "status": "error", "error": str(e)})

    logger.info(f"{provider} embedding worker (PID={pid}) exiting cleanly.")
