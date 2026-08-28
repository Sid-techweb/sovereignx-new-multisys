import json
from pathlib import Path
from typing import Dict, List, Optional
from app.config import settings

class DocumentMetadataStore:
    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = settings.DOCUMENT_STORAGE_PATH
        
        self.base_path = Path(base_path).resolve()
        self.metadata_file = self.base_path / "metadata.json"
        
        # Ensure directories exist
        self.base_path.mkdir(parents=True, exist_ok=True)
        if not self.metadata_file.exists():
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _read_all(self) -> dict:
        try:
            if not self.metadata_file.exists():
                return {}
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_all(self, data: dict):
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save(self, doc_id: str, doc_data: dict):
        all_data = self._read_all()
        all_data[doc_id] = doc_data
        self._write_all(all_data)

    def get(self, doc_id: str) -> Optional[dict]:
        all_data = self._read_all()
        return all_data.get(doc_id)

    def get_all(self) -> List[dict]:
        all_data = self._read_all()
        return list(all_data.values())

    def delete(self, doc_id: str):
        all_data = self._read_all()
        if doc_id in all_data:
            del all_data[doc_id]
            self._write_all(all_data)
