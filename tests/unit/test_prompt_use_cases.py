# tests/unit/test_prompt_use_cases.py
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.use_cases.create_prompt import CreatePromptUseCase
from src.application.use_cases.get_prompt import GetPromptUseCase
from src.application.use_cases.update_prompt import UpdatePromptUseCase
from src.domain.entities.prompt import Prompt, PromptVersion


def _make_prompt(identifier: str = "test-prompt") -> Prompt:
    return Prompt(
        identifier=identifier,
        description="Test description",
        current_version=PromptVersion(
            version_id="v1",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
            tags=[],
        ),
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def mock_prompt_manager():
    manager = MagicMock()
    manager.get_prompt = AsyncMock()
    manager.create_prompt = AsyncMock()
    manager.update_prompt = AsyncMock()
    return manager


class TestCreatePromptUseCase:
    async def test_execute_success(self, mock_prompt_manager):
        expected = _make_prompt()
        mock_prompt_manager.create_prompt.return_value = expected

        use_case = CreatePromptUseCase(mock_prompt_manager)
        result = await use_case.execute(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
            description="Test description",
            tags=["tag1"],
        )

        assert result == expected
        mock_prompt_manager.create_prompt.assert_called_once_with(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
            description="Test description",
            tags=["tag1"],
            metadata=None,
        )

    async def test_execute_propagates_exception(self, mock_prompt_manager):
        mock_prompt_manager.create_prompt.side_effect = ValueError("already exists")

        use_case = CreatePromptUseCase(mock_prompt_manager)
        with pytest.raises(ValueError, match="already exists"):
            await use_case.execute(
                identifier="test-prompt",
                content=[{"role": "user", "content": "Hello"}],
                model_name="gpt-4",
            )

    async def test_execute_without_optional_fields(self, mock_prompt_manager):
        expected = _make_prompt()
        mock_prompt_manager.create_prompt.return_value = expected

        use_case = CreatePromptUseCase(mock_prompt_manager)
        result = await use_case.execute(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
        )

        assert result == expected
        mock_prompt_manager.create_prompt.assert_called_once_with(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
            description=None,
            tags=None,
            metadata=None,
        )


class TestGetPromptUseCase:
    async def test_execute_success(self, mock_prompt_manager):
        expected = _make_prompt()
        mock_prompt_manager.get_prompt.return_value = expected

        use_case = GetPromptUseCase(mock_prompt_manager)
        result = await use_case.execute(identifier="test-prompt")

        assert result == expected
        mock_prompt_manager.get_prompt.assert_called_once_with(
            identifier="test-prompt",
            version_id=None,
            tag=None,
        )

    async def test_execute_with_version_id(self, mock_prompt_manager):
        expected = _make_prompt()
        mock_prompt_manager.get_prompt.return_value = expected

        use_case = GetPromptUseCase(mock_prompt_manager)
        result = await use_case.execute(identifier="test-prompt", version_id="v2")

        assert result == expected
        mock_prompt_manager.get_prompt.assert_called_once_with(
            identifier="test-prompt",
            version_id="v2",
            tag=None,
        )

    async def test_execute_with_tag(self, mock_prompt_manager):
        expected = _make_prompt()
        mock_prompt_manager.get_prompt.return_value = expected

        use_case = GetPromptUseCase(mock_prompt_manager)
        result = await use_case.execute(identifier="test-prompt", tag="production")

        assert result == expected
        mock_prompt_manager.get_prompt.assert_called_once_with(
            identifier="test-prompt",
            version_id=None,
            tag="production",
        )

    async def test_execute_not_found_raises(self, mock_prompt_manager):
        mock_prompt_manager.get_prompt.side_effect = ValueError("Prompt not found: test-prompt")

        use_case = GetPromptUseCase(mock_prompt_manager)
        with pytest.raises(ValueError, match="not found"):
            await use_case.execute(identifier="test-prompt")


class TestUpdatePromptUseCase:
    async def test_execute_success(self, mock_prompt_manager):
        expected = _make_prompt()
        mock_prompt_manager.update_prompt.return_value = expected

        use_case = UpdatePromptUseCase(mock_prompt_manager)
        result = await use_case.execute(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Updated"}],
            model_name="gpt-4",
            description="Updated description",
        )

        assert result == expected
        mock_prompt_manager.update_prompt.assert_called_once_with(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Updated"}],
            model_name="gpt-4",
            description="Updated description",
            metadata=None,
        )

    async def test_execute_partial_update(self, mock_prompt_manager):
        expected = _make_prompt()
        mock_prompt_manager.update_prompt.return_value = expected

        use_case = UpdatePromptUseCase(mock_prompt_manager)
        result = await use_case.execute(
            identifier="test-prompt",
            description="Only description updated",
        )

        assert result == expected
        mock_prompt_manager.update_prompt.assert_called_once_with(
            identifier="test-prompt",
            content=None,
            model_name=None,
            description="Only description updated",
            metadata=None,
        )

    async def test_execute_not_found_raises(self, mock_prompt_manager):
        mock_prompt_manager.update_prompt.side_effect = ValueError("Prompt not found: test-prompt")

        use_case = UpdatePromptUseCase(mock_prompt_manager)
        with pytest.raises(ValueError, match="not found"):
            await use_case.execute(identifier="test-prompt")

    async def test_execute_propagates_exception(self, mock_prompt_manager):
        mock_prompt_manager.update_prompt.side_effect = RuntimeError("Phoenix unavailable")

        use_case = UpdatePromptUseCase(mock_prompt_manager)
        with pytest.raises(RuntimeError, match="Phoenix unavailable"):
            await use_case.execute(identifier="test-prompt")