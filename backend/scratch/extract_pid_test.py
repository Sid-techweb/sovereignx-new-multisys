import os
import sys
import time
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.services.extractors import ImageExtractor

def main():
    pid_path = Path(backend_dir).parent / "scratch" / "CASE-001" / "pump_P204_PID.jpg"
    if not pid_path.exists():
        print(f"Error: P&ID image not found at {pid_path}")
        return
        
    print(f"Loading image from {pid_path}...")
    with open(pid_path, "rb") as f:
        file_content = f.read()
        
    print("Initializing ImageExtractor (Qwen2-VL)...")
    t0 = time.time()
    extractor = ImageExtractor()
    t_init = time.time() - t0
    print(f"ImageExtractor initialized in {t_init:.2f} seconds.")
    
    print("Running extraction (Qwen2-VL inference on CPU)...")
    t0 = time.time()
    text, metadata = extractor.extract(file_content, filename="pump_P204_PID.jpg")
    t_extract = time.time() - t0
    print(f"Extraction completed in {t_extract:.2f} seconds.")
    
    print("\n--- EXTRACTED TEXT ---")
    print(text)
    print("----------------------")
    print("Metadata:", metadata)

if __name__ == "__main__":
    main()
