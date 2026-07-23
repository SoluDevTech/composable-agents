"""Tests for PhoenixPromptManagerProvider.

The ``phoenix.client.Client`` is an external boundary and is patched in the
adapter module. The adapter returns domain ``PromptVersion`` / ``Prompt``
entities (not Phoenix types).

Tests verify observable behavior (return values) rather than spying on the
internal ``_client`` attribute. Where the external client mock must be
configured, we set it up via the patched ``Client`` constructor return value.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domain.entities.prompt import Prompt, PromptVersion
from src.domain.errors.prompt import PromptNotFoundError
from src.infrastructure.prompt_management.adapter import PhoenixPromptManagerProvider


def _make_phoenix_prompt_obj(
    pid="v1",
    description="Test description",
    model_name="gpt-4",
    messages=None,
):
    """Build a mock Phoenix PromptVersion object with the private attrs the adapter reads."""
    obj = MagicMock()
    obj.id = pid
    obj._description = description
    obj._model_name = model_name
    obj._template = {"messages": messages or [{"role": "user", "content": "Hello"}]}
    return obj


def _make_client_mock(prompt_obj=None, tags_list=None):
    """Build a mock Phoenix client with prompts.get/create and tags.list/create."""
    client = MagicMock()
    client.prompts.get = MagicMock(return_value=prompt_obj)
    client.prompts.create = MagicMock(return_value=prompt_obj or _make_phoenix_prompt_obj())
    client.prompts.tags.list = MagicMock(return_value=tags_list or [])
    client.prompts.tags.create = MagicMock()
    return client


class TestPhoenixPromptManagerProviderCreate:
    """Tests for create_prompt — verify domain PromptVersion return value."""

    @pytest.fixture
    def manager(self):
        with patch("src.infrastructure.prompt_management.adapter.Client") as mock_client_cls:
            client = _make_client_mock(_make_phoenix_prompt_obj())
            mock_client_cls.return_value = client
            return PhoenixPromptManagerProvider(base_url="http://localhost:6006", api_key="test-key")

    async def test_create_prompt_returns_domain_prompt_version(self, manager):
        # Arrange
        content = [{"role": "user", "content": "Hello"}]

        # Act
        result = await manager.create_prompt(
            identifier="test-prompt",
            content=content,
            model_name="gpt-4",
            description="Test description",
            tags=["tag1"],
        )

        # Assert
        assert isinstance(result, PromptVersion)
        assert result.version_id == "v1"
        assert result.model_name == "gpt-4"
        assert result.content == content

    async def test_create_prompt_with_tags_returns_version_with_tags(self, manager):
        # Arrange
        content = [{"role": "user", "content": "Hello"}]

        # Act
        result = await manager.create_prompt(
            identifier="test-prompt",
            content=content,
            model_name="gpt-4",
            tags=["tag1", "tag2"],
        )

        # Assert
        assert isinstance(result, PromptVersion)
        assert result.tags == ["tag1", "tag2"]


class TestPhoenixPromptManagerProviderGet:
    """Tests for get_prompt — verify domain Prompt return value."""

    @pytest.fixture
    def manager(self):
        with patch("src.infrastructure.prompt_management.adapter.Client") as mock_client_cls:
            prompt_obj = _make_phoenix_prompt_obj(messages=[{"role": "system", "content": "Hello"}])
            client = _make_client_mock(prompt_obj, tags_list=[{"name": "production"}])
            mock_client_cls.return_value = client
            return PhoenixPromptManagerProvider(base_url="http://localhost:6006", api_key="test-key")

    async def test_get_prompt_returns_domain_prompt(self, manager):
        # Arrange
        # Act
        result = await manager.get_prompt("test-prompt")

        # Assert
        assert isinstance(result, Prompt)
        assert result.identifier == "test-prompt"
        assert result.current_version.tags == ["production"]
        assert result.current_version.model_name == "gpt-4"

    async def test_get_prompt_returns_content_from_template(self, manager):
        # Arrange
        # Act
        result = await manager.get_prompt("test-prompt")

        # Assert
        assert result.current_version.content == [{"role": "system", "content": "Hello"}]


class TestPhoenixPromptManagerProviderGetNotFound:
    """Tests for get_prompt when the prompt does not exist."""

    @pytest.fixture
    def manager(self):
        with patch("src.infrastructure.prompt_management.adapter.Client") as mock_client_cls:
            client = _make_client_mock(prompt_obj=None)
            mock_client_cls.return_value = client
            return PhoenixPromptManagerProvider(base_url="http://localhost:6006", api_key="test-key")

    async def test_get_prompt_not_found_raises(self, manager):
        # Arrange
        # Act & Assert
        with pytest.raises(PromptNotFoundError, match="Prompt not found"):
            await manager.get_prompt("nonexistent")


class TestPhoenixPromptManagerProviderAddTag:
    """Tests for add_tag — verify it completes without raising."""

    @pytest.fixture
    def manager(self):
        with patch("src.infrastructure.prompt_management.adapter.Client") as mock_client_cls:
            client = _make_client_mock()
            mock_client_cls.return_value = client
            return PhoenixPromptManagerProvider(base_url="http://localhost:6006", api_key="test-key")

    async def test_add_tag_completes_without_error(self, manager):
        # Arrange
        # Act
        await manager.add_tag("test-prompt", "new-tag")

        # Assert — add_tag returns None; verify it does not raise
