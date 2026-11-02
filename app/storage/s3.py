"""S3 storage backend stub."""

from pathlib import Path

from app.storage.base import StorageBackend


class S3Storage(StorageBackend):
    """S3 storage backend implementation stub."""

    def __init__(self, bucket_name: str = "") -> None:
        self.bucket_name = bucket_name

    def save(self, data: bytes, destination_path: str) -> str:
        """Save bytes to S3 bucket."""
        raise NotImplementedError

    def get(self, path: str) -> bytes:
        """Get bytes from S3 bucket."""
        raise NotImplementedError

    def get_local_path(self, path: str) -> Path:
        """Download to temp local path and return."""
        raise NotImplementedError
