"""Abstract base interface for storage backends."""

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    def save(self, data: bytes, destination_path: str) -> str:
        """Save bytes to destination path and return stored identifier or URI."""
        raise NotImplementedError

    @abstractmethod
    def get(self, path: str) -> bytes:
        """Retrieve bytes from stored identifier or path."""
        raise NotImplementedError

    @abstractmethod
    def get_local_path(self, path: str) -> Path:
        """Get accessible local filesystem Path."""
        raise NotImplementedError
