import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from sqlalchemy import text
from app.database import SessionLocal
from app.rag.indexer import KnowledgeBaseIndexer
from app.rag.retriever import KnowledgeBaseRetriever
from app.rag.embeddings import BGEM3EmbeddingProvider
from app.services.metadata_store import DocumentMetadataStore
from app.services.storage import LocalDocumentStorage
from app.services.extractors import PDFExtractor
from app.schemas.documents import ExtractedDocument
from app.rag.models import SQLDocumentChunk

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("live_verification")

def run_live_verification():
    db = SessionLocal()
    meta_store = DocumentMetadataStore()
    storage = LocalDocumentStorage()
    
    # 1. Clean existing table contents to start fresh
    logger.info("Cleaning document_chunks table...")
    db.query(SQLDocumentChunk).delete()
    db.commit()
    
    # 2. Setup embedder & indexer
    logger.info("Initializing BGEM3EmbeddingProvider and KnowledgeBaseIndexer...")
    embedder = BGEM3EmbeddingProvider()
    indexer = KnowledgeBaseIndexer(db, embedder)
    
    # Case-001 Documents to index
    docs_to_index = [
        ('b0153772-5f16-4d8b-85e1-124444efbc55', 'pump_P204_SOP.pdf'),
        ('5b36b9f9-c10b-4b9e-a84d-f54e072a89f1', 'pump_P204_inspection_report.pdf')
    ]
    
    total_indexed_chunks = 0
    pdf_extractor = PDFExtractor()
    for doc_id, filename in docs_to_index:
        logger.info(f"Loading extracted content for {filename} ({doc_id})...")
        meta = meta_store.get(doc_id)
        if not meta:
            logger.error(f"Metadata for {filename} not found!")
            continue
            
        # Re-run extraction locally to use the new PDFExtractor page break logic!
        ext = f".{meta['file_type']}"
        storage_name = f"{doc_id}{ext}"
        binary_content = storage.get(storage_name)
        
        extracted_text, extra_meta = pdf_extractor.extract(binary_content)
        
        extracted_doc = ExtractedDocument(
            document_id=doc_id,
            filename=filename,
            source=meta.get("source", "user_upload"),
            content=extracted_text,
            content_type="text",
            extraction_status="processed",
            metadata={
                **extra_meta,
                "mime_type": meta["mime_type"],
                "file_size": meta["file_size"],
                "uploaded_at": meta["uploaded_at"],
                "checksum_sha256": meta.get("checksum_sha256"),
                "case_id": meta.get("case_id")
            },
            created_at=meta.get("uploaded_at", "2026-08-26")
        )
        
        logger.info(f"Indexing {filename}...")
        chunks_indexed = indexer.index_document(extracted_doc)
        logger.info(f"Successfully indexed {chunks_indexed} chunks for {filename}.")
        total_indexed_chunks += chunks_indexed
        
    # 3. Verify records exist via catalog query (SQL)
    logger.info("Verifying document_chunks via direct SQL query...")
    result = db.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar()
    logger.info(f"SQL Row Count count: {result} (expected: {total_indexed_chunks})")
    
    # 4. Pick a chunk from the middle of the inspection report and verify page_number matches the physical PDF page.
    logger.info("Verifying PDF Page Provenance...")
    report_chunks = db.query(SQLDocumentChunk).filter(
        SQLDocumentChunk.filename == "pump_P204_inspection_report.pdf"
    ).order_by(SQLDocumentChunk.chunk_index).all()
    
    # Let's inspect a chunk from the middle
    mid_idx = len(report_chunks) // 2
    mid_chunk = report_chunks[mid_idx]
    logger.info(f"Middle Chunk index: {mid_chunk.chunk_index}")
    logger.info(f"Chunk page_number: {mid_chunk.page_number}")
    logger.info(f"Snippet: {mid_chunk.content[:250]}...")
    
    # 5. Perform a live duplicate check (indexing the same document unchanged)
    logger.info("Performing live duplicate indexing check...")
    doc_id, filename = docs_to_index[0]
    meta = meta_store.get(doc_id)
    storage_name = f"{doc_id}.pdf"
    binary_content = storage.get(storage_name)
    extracted_text, extra_meta = pdf_extractor.extract(binary_content)
    
    extracted_doc = ExtractedDocument(
        document_id=doc_id,
        filename=filename,
        source=meta.get("source", "user_upload"),
        content=extracted_text,
        content_type="text",
        extraction_status="processed",
        metadata={
            **extra_meta,
            "mime_type": meta["mime_type"],
            "file_size": meta["file_size"],
            "uploaded_at": meta["uploaded_at"],
            "checksum_sha256": meta.get("checksum_sha256"),
            "case_id": meta.get("case_id")
        },
        created_at=meta.get("uploaded_at", "2026-08-26")
    )
    dup_chunks = indexer.index_document(extracted_doc)
    logger.info(f"Re-indexed document chunk count returned: {dup_chunks} (should match original index count, not duplicate)")
    
    # Check total rows in DB after duplicate check (should be unchanged)
    dup_db_total = db.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar()
    logger.info(f"SQL Row Count after duplicate check: {dup_db_total} (should be same as: {total_indexed_chunks})")
    
    # 6. Perform a live stale check (modify checksum and content slightly, then re-index)
    logger.info("Performing live stale indexing check...")
    modified_meta = meta.copy()
    modified_meta["checksum_sha256"] = "new-checksum-sha256-test-stale-check"
    modified_content = extracted_text + "\n\n---SOVEREIGNX-PAGE-BREAK---\n\nAdded a new vibration safety threshold paragraph for test."
    modified_meta["page_count"] = extra_meta["page_count"] + 1
    
    modified_doc = ExtractedDocument(
        document_id=doc_id,
        filename=filename,
        source=meta.get("source", "user_upload"),
        content=modified_content,
        content_type="text",
        extraction_status="processed",
        metadata={
            **modified_meta,
            "page_count": modified_meta["page_count"]
        },
        created_at=meta.get("uploaded_at", "2026-08-26")
    )
    new_chunks_count = indexer.index_document(modified_doc)
    logger.info(f"Modified document re-indexed chunk count: {new_chunks_count}")
    
    # Check total rows in DB after stale check (should be new count + other document chunks)
    new_db_total = db.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar()
    logger.info(f"SQL Row Count after stale check: {new_db_total}")
    
    # 7. Execute semantic queries
    logger.info("Initializing KnowledgeBaseRetriever for semantic queries...")
    retriever = KnowledgeBaseRetriever(db, embedder)
    
    query_1 = "What does the SOP say about abnormal pump vibration?"
    logger.info(f"Running semantic query 1: '{query_1}'")
    results_1 = retriever.retrieve(query_1, top_k=3)
    
    logger.info("Query 1 Results:")
    for idx, r in enumerate(results_1):
        logger.info(f"[{idx+1}] File: {r['filename']} | Page: {r['metadata'].get('page_number')} | Score: {r['score']*100:.1f}%")
        logger.info(f"    Snippet: {r['content'][:250]}...")
        
    # Query 2 using a near-exact phrase from the SOP (e.g. bearing housing temperature maximum limit)
    query_2 = "Maximum permitted temperature bearing housing limit is 80"
    logger.info(f"Running semantic query 2: '{query_2}'")
    results_2 = retriever.retrieve(query_2, top_k=3)
    
    logger.info("Query 2 Results:")
    for idx, r in enumerate(results_2):
        logger.info(f"[{idx+1}] File: {r['filename']} | Page: {r['metadata'].get('page_number')} | Score: {r['score']*100:.1f}%")
        logger.info(f"    Snippet: {r['content'][:250]}...")
        
    db.close()

if __name__ == "__main__":
    run_live_verification()
