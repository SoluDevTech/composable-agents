"""Tests for CreatePromptUseCase, GetPromptUseCase, UpdatePromptUseCase.

Uses the shared ``mock_prompt_manager`` fixture from external.py (external
Phoenix boundary). Use cases return domain ``PromptVersion`` / ``Prompt``.
"""

from datetime import datetime

import pytest

from src.application.use_cases.create_prompt import CreatePromptUseCase
from src.application.use_cases.get_prompt import GetPromptUseCase
from src.application.use_cases.update_prompt import UpdatePromptUseCase
from src.domain.entities.prompt import Prompt, PromptVersion
from src.domain.errors.prompt import (
    PromptAlreadyExistsError,
    PromptManagerUnavailableError,
    PromptNotFoundError,
)


def _make_prompt_version(_identifier: str = "test-prompt") -> PromptVersion:
    return PromptVersion(
        version_id="v1",
        content=[{"role": "user", "content": "Hello"}],
        model_name="gpt-4",
        tags=[],
        created_at=datetime.now(),
    )


def _make_prompt(identifier: str = "test-prompt") -> Prompt:
    return Prompt(
        identifier=identifier,
        description="Test description",
        current_version=_make_prompt_version(identifier),
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestCreatePromptUseCase:
    @pytest.fixture
    def use_case(self, mock_prompt_manager):
        return CreatePromptUseCase(mock_prompt_manager)

    async def test_execute_returns_prompt_version(self, use_case, mock_prompt_manager):
        # Arrange
        expected = _make_prompt_version()
        mock_prompt_manager.create_prompt.return_value = expected

        # Act
        result = await use_case.execute(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
            description="Test description",
            tags=["tag1"],
        )

        # Assert
        assert result == expected

    async def test_execute_passes_all_args_to_manager(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.create_prompt.return_value = _make_prompt_version()

        # Act
        await use_case.execute(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
            description="Test description",
            tags=["tag1"],
        )

        # Assert
        mock_prompt_manager.create_prompt.assert_called_once_with(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
            description="Test description",
            tags=["tag1"],
            metadata=None,
        )

    async def test_execute_propagates_already_exists_error(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.create_prompt.side_effect = PromptAlreadyExistsError("already exists")

        # Act & Assert
        with pytest.raises(PromptAlreadyExistsError, match="already exists"):
            await use_case.execute(
                identifier="test-prompt",
                content=[{"role": "user", "content": "Hello"}],
                model_name="gpt-4",
            )

    async def test_execute_without_optional_fields_passes_none(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.create_prompt.return_value = _make_prompt_version()

        # Act
        await use_case.execute(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
        )

        # Assert
        mock_prompt_manager.create_prompt.assert_called_once_with(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Hello"}],
            model_name="gpt-4",
            description=None,
            tags=None,
            metadata=None,
        )


class TestGetPromptUseCase:
    @pytest.fixture
    def use_case(self, mock_prompt_manager):
        return GetPromptUseCase(mock_prompt_manager)

    async def test_execute_returns_prompt(self, use_case, mock_prompt_manager):
        # Arrange
        expected = _make_prompt()
        mock_prompt_manager.get_prompt.return_value = expected

        # Act
        result = await use_case.execute(identifier="test-prompt")

        # Assert
        assert result == expected

    async def test_execute_with_version_id_passes_through(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.get_prompt.return_value = _make_prompt()

        # Act
        await use_case.execute(identifier="test-prompt", version_id="v2")

        # Assert
        mock_prompt_manager.get_prompt.assert_called_once_with(
            identifier="test-prompt",
            version_id="v2",
            tag=None,
        )

    async def test_execute_with_tag_passes_through(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.get_prompt.return_value = _make_prompt()

        # Act
        await use_case.execute(identifier="test-prompt", tag="production")

        # Assert
        mock_prompt_manager.get_prompt.assert_called_once_with(
            identifier="test-prompt",
            version_id=None,
            tag="production",
        )

    async def test_execute_not_found_raises(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.get_prompt.side_effect = PromptNotFoundError("Prompt not found: test-prompt")

        # Act & Assert
        with pytest.raises(PromptNotFoundError, match="not found"):
            await use_case.execute(identifier="test-prompt")


class TestUpdatePromptUseCase:
    @pytest.fixture
    def use_case(self, mock_prompt_manager):
        return UpdatePromptUseCase(mock_prompt_manager)

    async def test_execute_returns_prompt_version(self, use_case, mock_prompt_manager):
        # Arrange
        expected = _make_prompt_version()
        mock_prompt_manager.update_prompt.return_value = expected

        # Act
        result = await use_case.execute(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Updated"}],
            model_name="gpt-4",
            description="Updated description",
        )

        # Assert
        assert result == expected

    async def test_execute_passes_all_args_to_manager(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.update_prompt.return_value = _make_prompt_version()

        # Act
        await use_case.execute(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Updated"}],
            model_name="gpt-4",
            description="Updated description",
        )

        # Assert
        mock_prompt_manager.update_prompt.assert_called_once_with(
            identifier="test-prompt",
            content=[{"role": "user", "content": "Updated"}],
            model_name="gpt-4",
            description="Updated description",
            metadata=None,
        )

    async def test_execute_partial_update_passes_none_for_omitted(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.update_prompt.return_value = _make_prompt_version()

        # Act
        await use_case.execute(
            identifier="test-prompt",
            description="Only description updated",
        )

        # Assert
        mock_prompt_manager.update_prompt.assert_called_once_with(
            identifier="test-prompt",
            content=None,
            model_name=None,
            description="Only description updated",
            metadata=None,
        )

    async def test_execute_not_found_raises(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.update_prompt.side_effect = PromptNotFoundError("Prompt not found: test-prompt")

        # Act & Assert
        with pytest.raises(PromptNotFoundError, match="not found"):
            await use_case.execute(identifier="test-prompt")

    async def test_execute_propagates_unavailable_error(self, use_case, mock_prompt_manager):
        # Arrange
        mock_prompt_manager.update_prompt.side_effect = PromptManagerUnavailableError("Phoenix unavailable")

        # Act & Assert
        with pytest.raises(PromptManagerUnavailableError, match="Phoenix unavailable"):
            await use_case.execute(identifier="test-prompt")
