import os
from abc import ABC, abstractmethod
from pathlib import Path
from app.config import settings

class DocumentStorage(ABC):
    @abstractmethod
    def save(self, file_id: str, content: bytes) -> str:
        """Saves file content and returns the file identifier/path."""
        pass

    @abstractmethod
    def get(self, file_id: str) -> bytes:
        """Retrieves file content by identifier."""
        pass

    @abstractmethod
    def exists(self, file_id: str) -> bool:
        """Checks if file exists by identifier."""
        pass

    @abstractmethod
    def delete(self, file_id: str):
        """Deletes file by identifier."""
        pass

class LocalDocumentStorage(DocumentStorage):
    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = settings.DOCUMENT_STORAGE_PATH
        
        # Convert relative path to absolute relative to backend root
        self.base_path = Path(base_path).resolve()
        self.files_path = self.base_path / "files"
        # Ensure directories exist
        self.files_path.mkdir(parents=True, exist_ok=True)

    def _get_secure_path(self, file_id: str) -> Path:
        # Prevent any path traversal
        safe_name = os.path.basename(file_id)
        target_path = (self.files_path / safe_name).resolve()
        # Verify the target path stays inside our files path
        if not target_path.is_relative_to(self.files_path.resolve()):
            raise ValueError("Path traversal attempt detected")
        return target_path

    def save(self, file_id: str, content: bytes) -> str:
        target_path = self._get_secure_path(file_id)
        with open(target_path, "wb") as f:
            f.write(content)
        return str(target_path)

    def get(self, file_id: str) -> bytes:
        target_path = self._get_secure_path(file_id)
        if not target_path.exists():
            raise FileNotFoundError(f"File {file_id} not found")
        with open(target_path, "rb") as f:
            return f.read()

    def exists(self, file_id: str) -> bool:
        try:
            target_path = self._get_secure_path(file_id)
            return target_path.exists()
        except ValueError:
            return False

    def delete(self, file_id: str):
        try:
            target_path = self._get_secure_path(file_id)
            if target_path.exists():
                os.remove(target_path)
        except ValueError:
            pass
