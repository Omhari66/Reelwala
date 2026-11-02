"""Local filesystem storage backend implementation."""

from pathlib import Path

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    """Local filesystem storage implementation."""

    def __init__(self, base_dir: str = "./data") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, destination_path: str) -> str:
        """Save bytes locally."""
        target = self.base_dir / destination_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target)

    def get(self, path: str) -> bytes:
        """Read bytes locally."""
        target = Path(path)
        if not target.is_absolute():
            target = self.base_dir / path
        return target.read_bytes()

    def get_local_path(self, path: str) -> Path:
        """Return local Path."""
        target = Path(path)
        if not target.is_absolute():
            target = self.base_dir / path
        return target
