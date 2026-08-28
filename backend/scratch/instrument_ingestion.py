import os
import time
import hashlib
import uuid
import sys
import pypdf
import io
from pathlib import Path

# Add backend directory dynamically to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.database import SessionLocal
from app.services.extractors import PDFExtractor
from app.rag.chunker import chunk_document
from app.rag.embeddings import BGEM3EmbeddingProvider
from app.rag.models import SQLDocumentChunk
from app.schemas.documents import ExtractedDocument

def run_pipeline(run_name, pdf_path, reuse_embedder=None):
    print(f"\n--- Starting Ingestion Pipeline: {run_name} ---")
    
    # 1. File read
    t_start = time.perf_counter()
    with open(pdf_path, "rb") as f:
        file_content = f.read()
    t_file_read = (time.perf_counter() - t_start) * 1000.0
    
    file_size_mb = len(file_content) / (1024 * 1024)
    print(f"File read: {t_file_read:.2f} ms (Size: {file_size_mb:.2f} MB)")
    
    # 2. PDF open/parsing
    t_start = time.perf_counter()
    reader = pypdf.PdfReader(io.BytesIO(file_content))
    pages_count = len(reader.pages)
    t_pdf_parse = (time.perf_counter() - t_start) * 1000.0
    print(f"PDF open/parsing: {t_pdf_parse:.2f} ms (Pages: {pages_count})")
    
    # 3. Text extraction
    t_start = time.perf_counter()
    extracted_pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            extracted_pages.append(text.strip())
    full_text = "\n\n---SOVEREIGNX-PAGE-BREAK---\n\n".join(extracted_pages).strip()
    t_text_extract = (time.perf_counter() - t_start) * 1000.0
    print(f"Text extraction: {t_text_extract:.2f} ms")
    
    # 4. Page/image rendering (not used for PDF in SovereignX)
    t_page_render = 0.0
    
    # 5. OCR (not used for PDF in SovereignX)
    t_ocr = 0.0
    
    # 6. Qwen2-VL inference (not used for PDF in SovereignX)
    t_qwen2_vl = 0.0
    
    # 7. Chunk creation
    t_start = time.perf_counter()
    document_id = str(uuid.uuid4())
    filename = Path(pdf_path).name
    checksum = hashlib.sha256(file_content).hexdigest()
    
    chunks_dto = chunk_document(
        document_id=document_id,
        filename=filename,
        source="user_upload",
        content=full_text,
        metadata={"page_count": pages_count, "has_text": len(full_text) > 0}
    )
    t_chunk_create = (time.perf_counter() - t_start) * 1000.0
    print(f"Chunk creation: {t_chunk_create:.2f} ms (Chunks created: {len(chunks_dto)})")
    
    # 8. BGE-M3 model load
    t_start = time.perf_counter()
    if reuse_embedder is None:
        embedding_provider = BGEM3EmbeddingProvider()
        embedding_provider.initialize()
    else:
        embedding_provider = reuse_embedder
        embedding_provider.initialize()
    t_bge_load = (time.perf_counter() - t_start) * 1000.0
    print(f"BGE-M3 model load: {t_bge_load:.2f} ms")
    
    # 9. BGE-M3 embedding generation
    t_start = time.perf_counter()
    texts = [chunk.content for chunk in chunks_dto]
    embeddings = embedding_provider.get_embeddings(texts)
    t_embedding_gen = (time.perf_counter() - t_start) * 1000.0
    print(f"BGE-M3 embedding generation: {t_embedding_gen:.2f} ms")
    
    # 10. PostgreSQL/pgvector insert
    t_start = time.perf_counter()
    db = SessionLocal()
    try:
        db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_checksum == checksum).delete()
        for idx, chunk_dto in enumerate(chunks_dto):
            sql_chunk = SQLDocumentChunk(
                chunk_id=chunk_dto.chunk_id,
                document_id=chunk_dto.document_id,
                filename=chunk_dto.filename,
                source=chunk_dto.source,
                content=chunk_dto.content,
                chunk_index=chunk_dto.chunk_index,
                page_number=chunk_dto.page_number,
                document_checksum=checksum,
                chunk_metadata=chunk_dto.chunk_metadata,
                embedding=embeddings[idx]
            )
            db.add(sql_chunk)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Database Error: {e}")
    finally:
        db.close()
    t_db_insert = (time.perf_counter() - t_start) * 1000.0
    print(f"PostgreSQL/pgvector insert: {t_db_insert:.2f} ms")
    
    total_time = t_file_read + t_pdf_parse + t_text_extract + t_page_render + t_ocr + t_qwen2_vl + t_chunk_create + t_bge_load + t_embedding_gen + t_db_insert
    print(f"Total Ingestion Time: {total_time:.2f} ms")
    
    return {
        "file_size_mb": file_size_mb,
        "pages": pages_count,
        "file_read": t_file_read,
        "pdf_parse": t_pdf_parse,
        "text_extract": t_text_extract,
        "ocr": t_ocr,
        "qwen2_vl": t_qwen2_vl,
        "chunk_create": t_chunk_create,
        "bge_load": t_bge_load,
        "embedding_gen": t_embedding_gen,
        "db_insert": t_db_insert,
        "total": total_time
    }, embedding_provider

def main():
    if len(sys.argv) < 2:
        print("Usage: python instrument_ingestion.py <path_to_pdf>")
        sys.exit(1)
        
    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"Error: File not found at '{pdf_path}'")
        sys.exit(1)
        
    # Run 1: Cold run
    cold_results, cold_embedder = run_pipeline("Cold Run", pdf_path)
    
    # Run 2: Warm run
    warm_results, _ = run_pipeline("Warm Run", pdf_path, reuse_embedder=cold_embedder)
    
    # Run 3: Warm run again
    warm2_results, _ = run_pipeline("Warm Run Again", pdf_path, reuse_embedder=cold_embedder)
    
    # Print comparison table
    print("\n================== LATENCY REPORT COMPARISON ==================")
    print(f"{'Stage':<30} | {'Cold Run (ms)':<15} | {'Warm Run (ms)':<15} | {'Warm Run 2 (ms)':<15}")
    print("-" * 85)
    stages = [
        ("File read", "file_read"),
        ("PDF parsing", "pdf_parse"),
        ("Text extraction", "text_extract"),
        ("OCR", "ocr"),
        ("Qwen2-VL", "qwen2_vl"),
        ("Chunking", "chunk_create"),
        ("BGE load", "bge_load"),
        ("Embedding", "embedding_gen"),
        ("DB insert", "db_insert"),
        ("Total", "total")
    ]
    for label, key in stages:
        print(f"{label:<30} | {cold_results[key]:<15.2f} | {warm_results[key]:<15.2f} | {warm2_results[key]:<15.2f}")
    print("==============================================================")

if __name__ == "__main__":
    main()
