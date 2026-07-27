"""Tests for per-user LLM credentials in the DeepAgent factory.

Verifies that ``create_agent_from_config`` builds a ``ChatOpenAI`` instance
with the user's ``base_url`` / ``api_key`` when an LLM credentials resolver is
provided AND the ``current_user_id`` contextvar is set. Falls back to the env
string-based model when no resolver / no contextvar (existing tests behaviour).

The deepagents ``create_deep_agent`` boundary is mocked so no real LLM is built.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_openai import ChatOpenAI

from src.domain.entities.agent_config import AgentConfig
from src.domain.errors.llm import LlmNotConfiguredError
from src.infrastructure.database.rls_context import current_user_id
from src.infrastructure.deepagent.factory import create_agent_from_config


def _captured_model(mock_create: MagicMock) -> Any:
    """Return the ``model`` kwarg passed to ``create_deep_agent``."""
    return mock_create.call_args.kwargs["model"]


class TestPerUserLlmCredentials:
    """When a resolver returns credentials and a user is set, build ChatOpenAI."""

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_resolver_returns_credentials_builds_chat_openai_instance(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent", model="gpt-4o-mini")
        token = current_user_id.set("u1")
        try:
            resolver = AsyncMock(return_value=("https://api.openai.com/v1", "sk-test"))

            # Act
            await create_agent_from_config(config, llm_credentials_resolver=resolver)

            # Assert
            kwargs = mock_create.call_args.kwargs
            model = kwargs["model"]
            assert isinstance(model, ChatOpenAI)
            assert model.openai_api_base == "https://api.openai.com/v1"
            # api_key stored as SecretStr — check the value
            assert model.openai_api_key is not None
            assert model.openai_api_key.get_secret_value() == "sk-test"
            assert model.model == "gpt-4o-mini"
        finally:
            current_user_id.reset(token)

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_resolver_returns_none_raises_llm_not_configured(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent")
        token = current_user_id.set("u1")
        try:
            resolver = AsyncMock(return_value=None)

            # Act & Assert
            with pytest.raises(LlmNotConfiguredError):
                await create_agent_from_config(config, llm_credentials_resolver=resolver)
        finally:
            current_user_id.reset(token)


class TestEnvFallback:
    """When no resolver is provided OR no user contextvar, fall back to env string model."""

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_no_resolver_keeps_string_model(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent")
        token = current_user_id.set("u1")
        try:
            # Act — no resolver provided
            await create_agent_from_config(config)

            # Assert — model is still the string
            kwargs = mock_create.call_args.kwargs
            assert isinstance(kwargs["model"], str)
            assert kwargs["model"] == "claude-sonnet-4-5-20250929"
        finally:
            current_user_id.reset(token)

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_no_user_contextvar_keeps_string_model_even_with_resolver(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent")
        # current_user_id is None by default in tests
        assert current_user_id.get() is None
        resolver = AsyncMock(return_value=("https://x", "sk-test"))

        # Act
        await create_agent_from_config(config, llm_credentials_resolver=resolver)

        # Assert — string fallback because no user contextvar
        kwargs = mock_create.call_args.kwargs
        assert isinstance(kwargs["model"], str)
        # The resolver was NOT called since there's no user
        resolver.assert_not_awaited()


class TestResolverSignature:
    """The factory accepts an optional ``llm_credentials_resolver`` callable."""

    def test_signature_accepts_resolver(self):
        import inspect

        sig = inspect.signature(create_agent_from_config)
        assert "llm_credentials_resolver" in sig.parameters
