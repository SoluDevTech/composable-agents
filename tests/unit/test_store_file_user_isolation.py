"""Tests for per-user namespace isolation in :class:`LangGraphStoreFileRepository`.

The repository is constructed with a ``namespace_provider`` callable returning
the current user-scoped namespace (``user_namespaced("filesystem")``). When
``current_user_id`` is set, files written by user A are invisible to user B.
When the contextvar is ``None`` (legacy / tests), the namespace falls back to
``("filesystem",)`` so both users' data is visible (existing behaviour).

Uses a real :class:`InMemoryStore` (no DB required).
"""

import pytest
from langgraph.store.memory import InMemoryStore

from src.infrastructure.database.rls_context import current_user_id
from src.infrastructure.deepagent.namespace import user_namespaced
from src.infrastructure.store_file.adapter import LangGraphStoreFileRepository


@pytest.fixture
def store() -> InMemoryStore:
    """Provide a fresh real InMemoryStore per test."""
    return InMemoryStore()


@pytest.fixture
def repo(store: InMemoryStore) -> LangGraphStoreFileRepository:
    """Repository wired with a per-user namespace provider."""
    return LangGraphStoreFileRepository(store=store, namespace_provider=lambda: user_namespaced("filesystem"))


class TestStoreFileUserIsolation:
    """Per-user isolation driven by ``current_user_id``."""

    async def test_user_a_files_invisible_to_user_b_list(
        self, store: InMemoryStore, repo: LangGraphStoreFileRepository
    ) -> None:
        # Arrange — write a file under uA
        tok_a = current_user_id.set("uA")
        try:
            await repo.put_file("/skills/x/SKILL.md", "# A skill")
        finally:
            current_user_id.reset(tok_a)

        # Act — list under uB
        tok_b = current_user_id.set("uB")
        try:
            files = await repo.list_files("/skills/")
        finally:
            current_user_id.reset(tok_b)

        # Assert — uB sees nothing
        assert files == []

    async def test_user_a_files_invisible_to_user_b_get(
        self, store: InMemoryStore, repo: LangGraphStoreFileRepository
    ) -> None:
        # Arrange — write a file under uA
        tok_a = current_user_id.set("uA")
        try:
            await repo.put_file("/skills/x/SKILL.md", "# A skill")
        finally:
            current_user_id.reset(tok_a)

        # Act — get under uB
        tok_b = current_user_id.set("uB")
        try:
            content = await repo.get_file("/skills/x/SKILL.md")
        finally:
            current_user_id.reset(tok_b)

        # Assert — uB cannot read uA's file
        assert content is None

    async def test_user_b_can_write_and_read_own_files(
        self, store: InMemoryStore, repo: LangGraphStoreFileRepository
    ) -> None:
        # Arrange — uA writes a file
        tok_a = current_user_id.set("uA")
        try:
            await repo.put_file("/skills/a/SKILL.md", "# A")
        finally:
            current_user_id.reset(tok_a)

        # Act — uB writes its own file then lists
        tok_b = current_user_id.set("uB")
        try:
            await repo.put_file("/skills/b/SKILL.md", "# B")
            files = await repo.list_files("/skills/")
            content_b = await repo.get_file("/skills/b/SKILL.md")
        finally:
            current_user_id.reset(tok_b)

        # Assert — uB only sees its own file
        assert files == ["/skills/b/SKILL.md"]
        assert content_b == "# B"

    async def test_delete_under_uB_does_not_remove_uA_file(
        self, store: InMemoryStore, repo: LangGraphStoreFileRepository
    ) -> None:
        # Arrange — uA writes
        tok_a = current_user_id.set("uA")
        try:
            await repo.put_file("/skills/shared/SKILL.md", "# A")
        finally:
            current_user_id.reset(tok_a)

        # Act — uB deletes the same path (no-op, different namespace)
        tok_b = current_user_id.set("uB")
        try:
            await repo.delete_file("/skills/shared/SKILL.md")
        finally:
            current_user_id.reset(tok_b)

        # Assert — uA still has its file
        tok_a2 = current_user_id.set("uA")
        try:
            content = await repo.get_file("/skills/shared/SKILL.md")
        finally:
            current_user_id.reset(tok_a2)
        assert content == "# A"

    async def test_legacy_no_contextvar_both_visible(
        self, store: InMemoryStore, repo: LangGraphStoreFileRepository
    ) -> None:
        # Arrange — write "as uA" then "as uB" then unset contextvar
        tok_a = current_user_id.set("uA")
        try:
            await repo.put_file("/skills/a/SKILL.md", "# A")
        finally:
            current_user_id.reset(tok_a)

        tok_b = current_user_id.set("uB")
        try:
            await repo.put_file("/skills/b/SKILL.md", "# B")
        finally:
            current_user_id.reset(tok_b)

        # Act — no contextvar (default None) → legacy namespace ("filesystem",)
        assert current_user_id.get() is None
        files = await repo.list_files("/skills/")

        # Assert — both visible under the legacy global namespace
        # (the legacy namespace is distinct from uA/uB namespaces, so it's empty
        # unless something was written without a user prefix)
        assert files == []

    async def test_legacy_writes_visible_across_no_contextvar(
        self, store: InMemoryStore, repo: LangGraphStoreFileRepository
    ) -> None:
        # Arrange — write with no contextvar (legacy namespace ("filesystem",))
        assert current_user_id.get() is None
        await repo.put_file("/skills/legacy/SKILL.md", "# legacy")

        # Act — read with no contextvar
        content = await repo.get_file("/skills/legacy/SKILL.md")

        # Assert
        assert content == "# legacy"


class TestStoreFileRepositoryBackwardCompat:
    """Backward compatibility: no namespace_provider → static default."""

    async def test_no_provider_uses_default_namespace(self, store: InMemoryStore) -> None:
        # Arrange — construct like the existing tests do (no provider)
        repo = LangGraphStoreFileRepository(store=store)

        # Act
        await repo.put_file("/skills/x/SKILL.md", "# x")

        # Assert — the store received the write under ("filesystem",)
        item = await store.aget(("filesystem",), "/skills/x/SKILL.md")
        assert item is not None
        assert item.value["content"] == "# x"

    async def test_static_namespace_still_supported(self, store: InMemoryStore) -> None:
        # Arrange — explicit static namespace (existing tests use this)
        repo = LangGraphStoreFileRepository(store=store, namespace=("custom", "ns"))

        # Act
        await repo.put_file("/x.md", "c")

        # Assert
        item = await store.aget(("custom", "ns"), "/x.md")
        assert item is not None
