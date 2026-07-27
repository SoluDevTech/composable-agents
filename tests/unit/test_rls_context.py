"""Tests for the RLS contextvars module.

The module exposes ``current_user_id``, ``current_credential`` and
``bypass_rls`` contextvars plus a ``system_rls_context`` async context manager
that temporarily enables RLS bypass for system/migration queries.
"""

import pytest

from src.infrastructure.database.rls_context import (
    bypass_rls,
    current_credential,
    current_user_id,
    system_rls_context,
)


class TestRlsContextDefaults:
    """Tests for contextvar default values."""

    def test_current_user_id_defaults_to_none(self) -> None:
        # Act & Assert
        assert current_user_id.get() is None

    def test_current_credential_defaults_to_none(self) -> None:
        # Act & Assert
        assert current_credential.get() is None

    def test_bypass_rls_defaults_to_false(self) -> None:
        # Act & Assert
        assert bypass_rls.get() is False


class TestRlsContextSetGet:
    """Tests for setting/getting contextvars within a test."""

    def test_current_user_id_set_then_get_returns_value(self) -> None:
        # Arrange
        token = current_user_id.set("user-123")
        try:
            # Act & Assert
            assert current_user_id.get() == "user-123"
        finally:
            current_user_id.reset(token)
            assert current_user_id.get() is None

    def test_current_credential_set_then_get_returns_value(self) -> None:
        # Arrange
        token = current_credential.set("raw-jwt")
        try:
            # Act & Assert
            assert current_credential.get() == "raw-jwt"
        finally:
            current_credential.reset(token)
            assert current_credential.get() is None


class TestSystemRlsContext:
    """Tests for the ``system_rls_context`` async context manager."""

    async def test_system_rls_context_sets_bypass_true_inside(self) -> None:
        # Act & Assert
        async with system_rls_context():
            assert bypass_rls.get() is True

    async def test_system_rls_context_resets_bypass_after_exit(self) -> None:
        # Arrange
        assert bypass_rls.get() is False

        # Act
        async with system_rls_context():
            assert bypass_rls.get() is True

        # Assert
        assert bypass_rls.get() is False

    async def test_system_rls_context_resets_even_on_exception(self) -> None:
        # Arrange
        assert bypass_rls.get() is False

        # Act & Assert
        with pytest.raises(RuntimeError, match="boom"):
            async with system_rls_context():
                assert bypass_rls.get() is True
                raise RuntimeError("boom")

        # Assert — bypass reset after the exception propagated
        assert bypass_rls.get() is False
