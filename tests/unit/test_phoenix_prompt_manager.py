"""Tests for PhoenixPromptManagerProvider."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from phoenix.client.resources.prompts import PromptVersion as PhoenixPromptVersion

from src.infrastructure.prompt_management.phoenix_prompt_adapter import PhoenixPromptManagerProvider


class TestPhoenixPromptManagerProvider:
    @pytest.fixture
    def manager(self):
        with patch("src.infrastructure.prompt_management.phoenix_prompt_adapter.Client"):
            return PhoenixPromptManagerProvider(base_url="http://localhost:6006", api_key="test-key")

    @pytest.mark.asyncio
    async def test_create_prompt_success(self, manager):
        mock_prompt_obj = MagicMock(spec=PhoenixPromptVersion)
        mock_prompt_obj.id = "v1"
        mock_prompt_obj._description = "Test description"
        mock_prompt_obj._model_name = "gpt-4"
        mock_prompt_obj._template = {"messages": [{"role": "user", "content": "Hello"}]}

        manager._client.prompts.create = MagicMock(return_value=mock_prompt_obj)

        content = [{"role": "user", "content": "Hello"}]
        result = await manager.create_prompt(
            identifier="test-prompt",
            content=content,
            model_name="gpt-4",
            description="Test description",
            tags=["tag1"],
        )

        assert result.id == "v1"
        assert result._model_name == "gpt-4"
        assert result._description == "Test description"
        manager._client.prompts.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_prompt_with_tags(self, manager):
        mock_prompt_obj = MagicMock()
        mock_prompt_obj.name = "test-prompt"
        mock_prompt_obj.description = None
        mock_prompt_obj.version_id = "v1"
        mock_prompt_obj.content = []
        mock_prompt_obj.model_name = "gpt-4"
        mock_prompt_obj.created_at = datetime.now()
        mock_prompt_obj.updated_at = datetime.now()
        mock_prompt_obj.tags = []

        manager._client.prompts.create = MagicMock(return_value=mock_prompt_obj)
        manager._client.prompts.tag = MagicMock()

        await manager.create_prompt(
            identifier="test-prompt",
            content=[],
            model_name="gpt-4",
            tags=["tag1", "tag2"],
        )

        assert manager._client.prompts.tag.call_count == 2

    @pytest.mark.asyncio
    async def test_get_prompt_not_found(self, manager):
        manager._client.prompts.get = MagicMock(return_value=None)

        with pytest.raises(ValueError, match="Prompt not found"):
            await manager.get_prompt("nonexistent")

    @pytest.mark.asyncio
    async def test_add_tag(self, manager):
        manager._client.prompts.tag = MagicMock()

        await manager.add_tag("test-prompt", "new-tag")

        manager._client.prompts.tag.assert_called_once_with(prompt_identifier="test-prompt", tag="new-tag")
