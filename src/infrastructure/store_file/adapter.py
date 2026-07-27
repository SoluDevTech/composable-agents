"""LangGraph ``BaseStore`` adapter implementing :class:`StoreFileRepository`."""

from collections.abc import Callable

from langgraph.store.base import BaseStore

from src.domain.ports.store_file_repository import StoreFilePreview, StoreFileRepository

_DEFAULT_NAMESPACE: tuple[str, ...] = ("filesystem",)


class LangGraphStoreFileRepository(StoreFileRepository):
    """Store file repository backed by a LangGraph ``BaseStore``.

    Files are stored as key-value pairs where the key is the file path and
    the value is ``{"content": str, "encoding": "utf-8"}``.

    The namespace can be supplied either as a static tuple (``namespace``) or
    as a callable (``namespace_provider``) evaluated on each method call.
    The callable form enables per-user isolation: wire it to
    ``lambda: user_namespaced("filesystem")`` so the namespace becomes
    ``(user_id, "filesystem")`` when ``current_user_id`` is set, and falls
    back to ``("filesystem",)`` when it is ``None`` (legacy / tests).

    When neither argument is provided, the default static namespace
    ``("filesystem",)`` is used (backward compatibility with existing tests
    that construct ``LangGraphStoreFileRepository(store=...)``).
    """

    def __init__(
        self,
        store: BaseStore,
        namespace: tuple[str, ...] | None = None,
        namespace_provider: Callable[[], tuple[str, ...]] | None = None,
    ) -> None:
        """Initialize the repository.

        Args:
            store: The LangGraph ``BaseStore`` instance (InMemoryStore or AsyncPostgresStore).
            namespace: Static namespace tuple for scoping files. Ignored when
                ``namespace_provider`` is provided. Defaults to
                ``("filesystem",)`` when both ``namespace`` and
                ``namespace_provider`` are ``None``.
            namespace_provider: Optional callable returning the current
                namespace tuple, evaluated on each method call. Enables
                per-user isolation (e.g. ``lambda: user_namespaced("filesystem")``).

        Raises:
            ValueError: If both ``namespace`` and ``namespace_provider`` are
                provided (ambiguous configuration).
        """
        if namespace is not None and namespace_provider is not None:
            raise ValueError("Provide either 'namespace' or 'namespace_provider', not both")
        self._store = store
        self._namespace_provider = namespace_provider
        # Only used when no provider is given (static default / explicit override).
        self._static_namespace = namespace if namespace is not None else _DEFAULT_NAMESPACE

    def _resolve_namespace(self) -> tuple[str, ...]:
        """Resolve the namespace for the current call.

        When a ``namespace_provider`` is configured, it is evaluated on each
        call so the namespace reflects the current ``current_user_id``
        contextvar. Otherwise the static namespace is returned.

        Returns:
            The namespace tuple to scope store operations.
        """
        if self._namespace_provider is not None:
            return self._namespace_provider()
        return self._static_namespace

    async def list_files(self, prefix: str) -> list[str]:
        """List file paths in the store that start with the given prefix.

        Args:
            prefix: Path prefix to filter on.

        Returns:
            A list of file path strings matching the prefix.
        """
        ns = self._resolve_namespace()
        items = await self._store.asearch(ns, limit=1000)
        return [item.key for item in items if item.key.startswith(prefix)]

    async def list_files_with_preview(self, prefix: str, preview_chars: int) -> list[StoreFilePreview]:
        """List files matching prefix, each with a truncated content preview.

        Uses the values already returned by ``asearch`` — no extra DB reads.

        Args:
            prefix: Path prefix to filter on.
            preview_chars: Maximum characters to include in each preview.

        Returns:
            A list of ``StoreFilePreview`` objects.
        """
        ns = self._resolve_namespace()
        items = await self._store.asearch(ns, limit=1000)
        return [
            StoreFilePreview(
                path=item.key,
                preview=str(item.value.get("content", ""))[:preview_chars],
            )
            for item in items
            if item.key.startswith(prefix)
        ]

    async def get_file(self, path: str) -> str | None:
        """Get file content by path.

        Args:
            path: The file path to retrieve.

        Returns:
            The file content as a string, or ``None`` if not found or
            the stored value is malformed (missing ``content`` key).
        """
        ns = self._resolve_namespace()
        item = await self._store.aget(ns, path)
        if item is None:
            return None
        return item.value.get("content")

    async def put_file(self, path: str, content: str) -> None:
        """Create or replace a file in the store.

        Args:
            path: The file path to write.
            content: The UTF-8 text content to store.
        """
        ns = self._resolve_namespace()
        await self._store.aput(ns, path, {"content": content, "encoding": "utf-8"})

    async def delete_file(self, path: str) -> None:
        """Delete a file from the store.

        Idempotent: no error is raised if the path does not exist.

        Args:
            path: The file path to delete.
        """
        ns = self._resolve_namespace()
        await self._store.adelete(ns, path)
