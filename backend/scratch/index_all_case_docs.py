import os
import sys
import time
from pathlib import Path
from fastapi.testclient import TestClient

backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.main import app
from app.database import SessionLocal
from app.rag.models import SQLDocumentChunk

def main():
    client = TestClient(app)
    case_dir = Path(backend_dir).parent / "scratch" / "CASE-001"
    
    files = [
        "pump_P204_SOP.pdf",
        "pump_P204_sensor_data.csv",
        "pump_P204_inspection_report.pdf",
        "pump_P204_past_incident_report.pdf",
        "pump_P204_PID.jpg",
        "pump_P204_photo.jpg"
    ]
    
    print("Cleaning database table document_chunks...")
    db = SessionLocal()
    db.query(SQLDocumentChunk).delete()
    db.commit()
    db.close()
    
    print("\nStarting uploading and processing for all 6 CASE-001 documents...\n")
    
    for filename in files:
        file_path = case_dir / filename
        if not file_path.exists():
            print(f"Error: {filename} not found at {file_path}")
            continue
            
        print(f"--- Processing {filename} ({file_path.stat().st_size / 1024:.2f} KB) ---")
        
        # 1. Upload
        t0 = time.time()
        with open(file_path, "rb") as f:
            upload_res = client.post(
                "/documents/upload",
                files={"file": (filename, f.read(), "image/jpeg" if filename.endswith(".jpg") else "application/pdf" if filename.endswith(".pdf") else "text/csv")}
            )
            
        if upload_res.status_code != 201:
            print(f"Upload failed for {filename}: {upload_res.status_code} - {upload_res.text}")
            continue
            
        doc_id = upload_res.json()["document_id"]
        print(f"Uploaded successfully. Document ID: {doc_id} in {time.time() - t0:.2f}s")
        
        # 2. Process / Extract
        t0 = time.time()
        print(f"Triggering content extraction for {filename}...")
        proc_res = client.post(f"/documents/{doc_id}/process")
        if proc_res.status_code != 200:
            print(f"Processing failed for {filename}: {proc_res.status_code} - {proc_res.text}")
            continue
            
        print(f"Processed successfully in {time.time() - t0:.2f}s")
        
        # 3. Index in Knowledge Base
        t0 = time.time()
        print(f"Triggering indexing for {filename}...")
        idx_res = client.post(f"/knowledge-base/index/{doc_id}")
        if idx_res.status_code != 201:
            print(f"Indexing failed for {filename}: {idx_res.status_code} - {idx_res.text}")
            continue
            
        print(f"Indexed successfully in {time.time() - t0:.2f}s. Chunks indexed: {idx_res.json()['chunks_created']}")
        
        # Print a short snippet of content
        content_res = client.get(f"/documents/{doc_id}/content")
        content_text = content_res.json()["content"] or ""
        snippet = content_text[:120].replace('\n', ' ')
        print(f"Content Snippet: {snippet}...\n")
        
    # Check total document chunks in SQL database
    db = SessionLocal()
    count = db.query(SQLDocumentChunk).count()
    print(f"Total chunks indexed in SQL database: {count}")
    db.close()

if __name__ == "__main__":
    main()
