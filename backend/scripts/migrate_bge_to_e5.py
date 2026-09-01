"""
One-time (but safely re-runnable) migration: backfill multilingual-e5-small
embeddings for existing document_chunks rows that only have a BGE-M3
embedding so far.

Design (Phase 8-9 of the E5 embedding migration):
  - REUSES existing parsed/chunked text (`SQLDocumentChunk.content`) --
    never reparses source PDFs, never re-uploads anything.
  - NEVER touches the existing `embedding` (BGE-M3) column or deletes any
    row -- purely additive, writes only to `embedding_e5` / `embedding_e5_model`.
  - Idempotent and resumable BY CONSTRUCTION: every batch is selected with
    `WHERE embedding_e5 IS NULL`, so a chunk that already has an E5 vector
    is never re-selected. There is no separate offset/checkpoint file to
    manage or get out of sync -- the database row's own NULL-ness IS the
    resume marker. Killing this script at any point and re-running it
    later picks up exactly where it left off, with zero duplicate work.
  - Processes in bounded batches (default 32 rows) so the whole knowledge
    base is never loaded into memory at once, no matter how large it grows.
  - Reports processed / skipped / failed / total counts, both per-batch
    (progress logging) and as a final summary.

Usage:
    python scripts/migrate_bge_to_e5.py [--batch-size 32] [--dry-run]

`--dry-run` selects and embeds normally but does not commit the UPDATEs --
useful for estimating total row count / time before committing to the real
run. Safe to Ctrl+C at any point; the current batch's transaction simply
rolls back (nothing partially written).
"""
import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List

# Make `app` importable regardless of the caller's cwd (repo root, backend/,
# or backend/scripts/) -- insert this script's parent directory (backend/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.rag.models import SQLDocumentChunk
from app.rag.embeddings import E5SmallEmbeddingProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sovereignx.migrate_bge_to_e5")


@dataclass
class MigrationReport:
    total_pending_at_start: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    failed_chunk_ids: List[str] = field(default_factory=list)
    embedding_seconds: float = 0.0
    db_write_seconds: float = 0.0


def _count_pending(db) -> int:
    return (
        db.query(SQLDocumentChunk)
        .filter(SQLDocumentChunk.embedding.isnot(None), SQLDocumentChunk.embedding_e5.is_(None))
        .count()
    )


def _fetch_batch(db, batch_size: int, after_chunk_id) -> List[SQLDocumentChunk]:
    """
    Keyset-paginated fetch: advances strictly past `after_chunk_id` on every
    call, in addition to the `embedding_e5 IS NULL` filter. The NULL filter
    alone is NOT sufficient to guarantee forward progress -- in --dry-run
    mode the batch's in-memory embedding_e5 assignment is rolled back
    (never persisted, by design: a dry run must write nothing), so without
    the keyset cursor the exact same "still NULL" rows would be re-selected
    forever. This was caught live: an early version looped indefinitely,
    re-processing the same 2 dev-DB rows tens of thousands of times before
    being killed. The cursor makes forward progress unconditional, in both
    dry-run and real runs.
    """
    q = db.query(SQLDocumentChunk).filter(
        SQLDocumentChunk.embedding.isnot(None), SQLDocumentChunk.embedding_e5.is_(None)
    )
    if after_chunk_id is not None:
        q = q.filter(SQLDocumentChunk.chunk_id > after_chunk_id)
    return q.order_by(SQLDocumentChunk.chunk_id).limit(batch_size).all()


def run_migration(db=None, batch_size: int = 32, dry_run: bool = False) -> MigrationReport:
    """
    Core migration loop, importable directly (used by the CLI entry point
    below and by tests) so its logic is exercised the same way in both.
    Accepts an existing `db` session (tests inject a fixture/mock); opens
    and manages its own SessionLocal() otherwise.
    """
    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    report = MigrationReport()
    provider = E5SmallEmbeddingProvider()

    try:
        report.total_pending_at_start = _count_pending(db)
        logger.info(f"Migration start: {report.total_pending_at_start} chunk(s) pending E5 backfill.")

        after_chunk_id = None
        while True:
            batch = _fetch_batch(db, batch_size, after_chunk_id)
            if not batch:
                break
            after_chunk_id = batch[-1].chunk_id  # unconditional forward progress -- see _fetch_batch docstring

            texts = [c.content for c in batch]
            t0 = time.perf_counter()
            try:
                embeddings = provider.embed_documents(texts)
            except Exception as e:
                logger.error(f"Batch embedding failed for {len(batch)} chunk(s): {e}")
                report.failed += len(batch)
                report.failed_chunk_ids.extend(c.chunk_id for c in batch)
                # Do not retry this batch in a tight loop against a
                # persistently-unavailable embedding model -- surface the
                # failure and stop; re-running the script later will pick
                # these exact rows back up (still NULL) once the underlying
                # issue is fixed.
                break
            report.embedding_seconds += time.perf_counter() - t0

            for chunk, emb in zip(batch, embeddings):
                chunk.embedding_e5 = emb
                chunk.embedding_e5_model = provider.model_name
                report.processed += 1

            t0 = time.perf_counter()
            if dry_run:
                db.rollback()
            else:
                db.commit()
            report.db_write_seconds += time.perf_counter() - t0

            logger.info(
                f"Batch complete: processed={report.processed} "
                f"failed={report.failed} remaining≈{max(report.total_pending_at_start - report.processed - report.failed, 0)}"
            )

        report.skipped = max(report.total_pending_at_start - report.processed - report.failed, 0)
        logger.info(
            f"Migration complete: total={report.total_pending_at_start} "
            f"processed={report.processed} skipped={report.skipped} failed={report.failed}"
        )
        return report
    finally:
        if owns_session:
            db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill multilingual-e5-small embeddings for existing document_chunks.")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t0 = time.perf_counter()
    report = run_migration(batch_size=args.batch_size, dry_run=args.dry_run)
    elapsed = time.perf_counter() - t0

    print(f"\n=== E5 migration report ===")
    print(f"total pending at start: {report.total_pending_at_start}")
    print(f"processed:              {report.processed}")
    print(f"skipped:                {report.skipped}")
    print(f"failed:                 {report.failed}")
    if report.failed_chunk_ids:
        print(f"failed chunk_ids:       {report.failed_chunk_ids}")
    print(f"embedding time:         {report.embedding_seconds:.2f}s")
    print(f"db write time:          {report.db_write_seconds:.2f}s")
    print(f"elapsed (total):        {elapsed:.1f}s")
    if report.processed:
        print(f"chunks/sec:             {report.processed / max(elapsed, 0.001):.2f}")
    if report.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
