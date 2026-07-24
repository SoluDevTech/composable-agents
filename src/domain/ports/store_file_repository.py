"""Outbound port: file repository backed by a key-value store."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class StoreFilePreview:
    """A file path with a truncated preview of its content."""

    path: str
    preview: str


class StoreFileRepository(ABC):
    """Interface for reading and writing files in a namespace-scoped store.

    Implementations wrap an external key-value store (e.g. LangGraph
    ``BaseStore``) and expose a simple file-centric CRUD contract.
    """

    @abstractmethod
    async def list_files(self, prefix: str) -> list[str]:
        """List file paths in the store that start with the given prefix.

        Args:
            prefix: Path prefix to filter on (e.g. ``"/skills/"``).

        Returns:
            A list of file path strings matching the prefix.
        """

    @abstractmethod
    async def list_files_with_preview(self, prefix: str, preview_chars: int) -> list[StoreFilePreview]:
        """List files matching prefix, each with the first ``preview_chars`` of content.

        Args:
            prefix: Path prefix to filter on.
            preview_chars: Maximum number of characters to include in each preview.

        Returns:
            A list of ``StoreFilePreview`` objects.
        """

    @abstractmethod
    async def get_file(self, path: str) -> str | None:
        """Get file content by path.

        Args:
            path: The file path to retrieve.

        Returns:
            The file content as a string, or ``None`` if not found.
        """

    @abstractmethod
    async def put_file(self, path: str, content: str) -> None:
        """Create or replace a file in the store.

        Args:
            path: The file path to write.
            content: The UTF-8 text content to store.
        """

    @abstractmethod
    async def delete_file(self, path: str) -> None:
        """Delete a file from the store.

        Idempotent: no error is raised if the path does not exist.

        Args:
            path: The file path to delete.
        """
