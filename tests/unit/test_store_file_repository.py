"""Tests for LangGraphStoreFileRepository.

The repository is an outbound adapter wrapping the LangGraph ``BaseStore``
(an external infrastructure dependency), so the ``BaseStore`` is mocked at
its boundary. The repository itself is exercised with its real
implementation.

These tests are written TDD-Red: ``src.infrastructure.store_file.adapter``
does not exist yet, so importing it raises ``ImportError`` and every test
fails until the adapter is implemented.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.store_file.adapter import LangGraphStoreFileRepository


@pytest.fixture
def mock_store() -> AsyncMock:
    """Provide an AsyncMock simulating a LangGraph BaseStore.

    Each method is configured with a sensible default return value so that
    individual tests only need to override the behaviour they exercise.
    """
    store = AsyncMock()
    store.asearch = AsyncMock(return_value=[])
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock(return_value=None)
    store.adelete = AsyncMock(return_value=None)
    return store


class TestLangGraphStoreFileRepository:
    """Tests for the LangGraph-backed StoreFileRepository adapter."""

    async def test_list_files_returns_empty_when_store_empty(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        result = await repo.list_files("/skills/")

        # Assert
        assert result == []
        mock_store.asearch.assert_called_once()

    async def test_list_files_filters_by_prefix(self, mock_store: AsyncMock) -> None:
        # Arrange — items expose ``.key`` and ``.value`` like LangGraph Item objects
        item_skills_rag = MagicMock(key="/skills/rag/SKILL.md", value={"content": "# RAG"})
        item_memories = MagicMock(key="/memories/AGENTS.md", value={"content": "# AGENTS"})
        item_skills_review = MagicMock(key="/skills/code-review/SKILL.md", value={"content": "# Review"})
        mock_store.asearch = AsyncMock(return_value=[item_skills_rag, item_memories, item_skills_review])

        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        result = await repo.list_files("/skills/")

        # Assert
        assert "/skills/rag/SKILL.md" in result
        assert "/skills/code-review/SKILL.md" in result
        assert "/memories/AGENTS.md" not in result

    async def test_list_files_returns_all_keys_when_prefix_is_root(self, mock_store: AsyncMock) -> None:
        # Arrange
        item1 = MagicMock(key="/skills/rag/SKILL.md", value={"content": "# RAG"})
        item2 = MagicMock(key="/memories/AGENTS.md", value={"content": "# AGENTS"})
        mock_store.asearch = AsyncMock(return_value=[item1, item2])

        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        result = await repo.list_files("/")

        # Assert
        assert len(result) == 2
        assert "/skills/rag/SKILL.md" in result
        assert "/memories/AGENTS.md" in result

    async def test_get_file_returns_content_when_exists(self, mock_store: AsyncMock) -> None:
        # Arrange
        mock_item = MagicMock(value={"content": "# My Skill", "encoding": "utf-8"})
        mock_store.aget = AsyncMock(return_value=mock_item)

        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        result = await repo.get_file("/skills/rag/SKILL.md")

        # Assert
        assert result == "# My Skill"
        mock_store.aget.assert_called_once_with(("filesystem",), "/skills/rag/SKILL.md")

    async def test_get_file_returns_none_when_not_found(self, mock_store: AsyncMock) -> None:
        # Arrange
        mock_store.aget = AsyncMock(return_value=None)

        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        result = await repo.get_file("/skills/nonexistent/SKILL.md")

        # Assert
        assert result is None

    async def test_get_file_returns_none_when_value_missing_content_key(self, mock_store: AsyncMock) -> None:
        # Arrange — defensive: malformed stored value without "content"
        mock_item = MagicMock(value={"encoding": "utf-8"})
        mock_store.aget = AsyncMock(return_value=mock_item)

        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        result = await repo.get_file("/skills/rag/SKILL.md")

        # Assert
        assert result is None

    async def test_put_file_stores_content_with_utf8_encoding(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        await repo.put_file("/skills/rag/SKILL.md", "# My Skill")

        # Assert
        mock_store.aput.assert_called_once()
        call_args = mock_store.aput.call_args
        # Positional contract: (namespace, key, value_dict)
        assert call_args.args[0] == ("filesystem",)
        assert call_args.args[1] == "/skills/rag/SKILL.md"
        assert call_args.args[2]["content"] == "# My Skill"
        assert call_args.args[2]["encoding"] == "utf-8"

    async def test_put_file_passes_through_unicode_content(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store)
        unicode_content = "# RAG\n\nBonjour café — naïve façade"

        # Act
        await repo.put_file("/skills/rag/SKILL.md", unicode_content)

        # Assert
        stored_value = mock_store.aput.call_args.args[2]
        assert stored_value["content"] == unicode_content

    async def test_delete_file_removes_from_store(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        await repo.delete_file("/skills/rag/SKILL.md")

        # Assert
        mock_store.adelete.assert_called_once_with(("filesystem",), "/skills/rag/SKILL.md")

    async def test_delete_file_is_idempotent_when_key_absent(self, mock_store: AsyncMock) -> None:
        # Arrange — BaseStore.adelete returns None even for missing keys
        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act — should not raise
        await repo.delete_file("/skills/does-not-exist/SKILL.md")

        # Assert
        mock_store.adelete.assert_called_once_with(("filesystem",), "/skills/does-not-exist/SKILL.md")

    async def test_uses_custom_namespace_for_get(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store, namespace=("custom", "ns"))

        # Act
        await repo.get_file("/test.md")

        # Assert
        mock_store.aget.assert_called_once_with(("custom", "ns"), "/test.md")

    async def test_uses_custom_namespace_for_put(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store, namespace=("custom",))

        # Act
        await repo.put_file("/test.md", "content")

        # Assert
        assert mock_store.aput.call_args.args[0] == ("custom",)

    async def test_uses_custom_namespace_for_delete(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store, namespace=("custom",))

        # Act
        await repo.delete_file("/test.md")

        # Assert
        mock_store.adelete.assert_called_once_with(("custom",), "/test.md")

    async def test_uses_custom_namespace_for_list(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store, namespace=("custom", "files"))

        # Act
        await repo.list_files("/")

        # Assert
        mock_store.asearch.assert_called_once()
        assert mock_store.asearch.call_args.args[0] == ("custom", "files")

    async def test_default_namespace_is_filesystem(self, mock_store: AsyncMock) -> None:
        # Arrange
        repo = LangGraphStoreFileRepository(store=mock_store)

        # Act
        await repo.get_file("/any.md")

        # Assert
        mock_store.aget.assert_called_once_with(("filesystem",), "/any.md")
