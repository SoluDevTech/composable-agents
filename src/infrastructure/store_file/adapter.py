"""LangGraph ``BaseStore`` adapter implementing :class:`StoreFileRepository`."""

from langgraph.store.base import BaseStore

from src.domain.ports.store_file_repository import StoreFileRepository

_DEFAULT_NAMESPACE: tuple[str, ...] = ("filesystem",)


class LangGraphStoreFileRepository(StoreFileRepository):
    """Store file repository backed by a LangGraph ``BaseStore``.

    Files are stored as key-value pairs where the key is the file path and
    the value is ``{"content": str, "encoding": "utf-8"}``.
    """

    def __init__(self, store: BaseStore, namespace: tuple[str, ...] = _DEFAULT_NAMESPACE) -> None:
        """Initialize the repository.

        Args:
            store: The LangGraph ``BaseStore`` instance (InMemoryStore or AsyncPostgresStore).
            namespace: Namespace tuple for scoping files (default ``("filesystem",)``).
        """
        self._store = store
        self._namespace = namespace

    async def list_files(self, prefix: str) -> list[str]:
        """List file paths in the store that start with the given prefix.

        Args:
            prefix: Path prefix to filter on.

        Returns:
            A list of file path strings matching the prefix.
        """
        items = await self._store.asearch(self._namespace, limit=100)
        return [item.key for item in items if item.key.startswith(prefix)]

    async def get_file(self, path: str) -> str | None:
        """Get file content by path.

        Args:
            path: The file path to retrieve.

        Returns:
            The file content as a string, or ``None`` if not found or
            the stored value is malformed (missing ``content`` key).
        """
        item = await self._store.aget(self._namespace, path)
        if item is None:
            return None
        return item.value.get("content")

    async def put_file(self, path: str, content: str) -> None:
        """Create or replace a file in the store.

        Args:
            path: The file path to write.
            content: The UTF-8 text content to store.
        """
        await self._store.aput(self._namespace, path, {"content": content, "encoding": "utf-8"})

    async def delete_file(self, path: str) -> None:
        """Delete a file from the store.

        Idempotent: no error is raised if the path does not exist.

        Args:
            path: The file path to delete.
        """
        await self._store.adelete(self._namespace, path)
