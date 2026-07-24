"""Use cases for managing files in the LangGraph store.

Each use case is a thin orchestrator that delegates to a
:class:`StoreFileRepository` (outbound port). The use cases contain no
business logic — they are pure pass-throughs following SRP (one class =
one action).
"""

from src.domain.ports.store_file_repository import StoreFileRepository


class ListStoreFilesUseCase:
    """List file paths in the store filtered by an optional prefix."""

    def __init__(self, repository: StoreFileRepository) -> None:
        """Initialize the use case.

        Args:
            repository: The store file repository (outbound port).
        """
        self._repository = repository

    async def execute(self, prefix: str = "/") -> list[str]:
        """List files matching the given prefix.

        Args:
            prefix: Path prefix to filter on (default ``"/"`` = all files).

        Returns:
            A list of file path strings.
        """
        return await self._repository.list_files(prefix)


class GetStoreFileUseCase:
    """Retrieve a single file's content by path."""

    def __init__(self, repository: StoreFileRepository) -> None:
        """Initialize the use case.

        Args:
            repository: The store file repository (outbound port).
        """
        self._repository = repository

    async def execute(self, path: str) -> str | None:
        """Get file content by path.

        Args:
            path: The file path to retrieve.

        Returns:
            The file content as a string, or ``None`` if not found.
        """
        return await self._repository.get_file(path)


class PutStoreFileUseCase:
    """Create or replace a file in the store."""

    def __init__(self, repository: StoreFileRepository) -> None:
        """Initialize the use case.

        Args:
            repository: The store file repository (outbound port).
        """
        self._repository = repository

    async def execute(self, path: str, content: str) -> str:
        """Store the given content at the given path.

        Args:
            path: The file path to write.
            content: The UTF-8 text content to store.

        Returns:
            The content that was stored.
        """
        await self._repository.put_file(path, content)
        return content


class DeleteStoreFileUseCase:
    """Delete a file from the store."""

    def __init__(self, repository: StoreFileRepository) -> None:
        """Initialize the use case.

        Args:
            repository: The store file repository (outbound port).
        """
        self._repository = repository

    async def execute(self, path: str) -> None:
        """Delete a file by path.

        Args:
            path: The file path to delete.
        """
        await self._repository.delete_file(path)
