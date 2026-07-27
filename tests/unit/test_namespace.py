"""Tests for the ``user_namespaced`` helper.

The helper builds a LangGraph Store namespace tuple prefixed by the current
authenticated user id (read from the ``current_user_id`` contextvar). When the
contextvar is ``None`` (no auth context, e.g. existing tests), the user prefix
is dropped so the namespace falls back to the legacy global tuple — keeping
all pre-existing tests green.
"""

from src.infrastructure.database.rls_context import current_user_id
from src.infrastructure.deepagent.namespace import user_namespaced


class TestUserNamespaced:
    """``user_namespaced`` resolves the namespace from the RLS contextvar."""

    def test_returns_user_prefixed_tuple_when_contextvar_set(self) -> None:
        # Arrange
        token = current_user_id.set("u1")
        try:
            # Act
            ns = user_namespaced("filesystem")
        finally:
            current_user_id.reset(token)

        # Assert
        assert ns == ("u1", "filesystem")

    def test_returns_legacy_tuple_when_contextvar_none(self) -> None:
        # Arrange — ensure default
        assert current_user_id.get() is None

        # Act
        ns = user_namespaced("filesystem")

        # Assert
        assert ns == ("filesystem",)

    def test_supports_multiple_suffix_segments(self) -> None:
        # Arrange
        token = current_user_id.set("uA")
        try:
            # Act
            ns = user_namespaced("agents", "agent1")
        finally:
            current_user_id.reset(token)

        # Assert
        assert ns == ("uA", "agents", "agent1")

    def test_multiple_suffix_legacy_when_none(self) -> None:
        # Arrange
        assert current_user_id.get() is None

        # Act
        ns = user_namespaced("agents", "agent1")

        # Assert
        assert ns == ("agents", "agent1")

    def test_empty_suffix_returns_just_user_id_when_set(self) -> None:
        # Arrange
        token = current_user_id.set("uX")
        try:
            # Act
            ns = user_namespaced()
        finally:
            current_user_id.reset(token)

        # Assert
        assert ns == ("uX",)

    def test_empty_suffix_returns_empty_tuple_when_none(self) -> None:
        # Arrange
        assert current_user_id.get() is None

        # Act
        ns = user_namespaced()

        # Assert
        assert ns == ()
