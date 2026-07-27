"""Tests for user-credential placeholder resolution in env_utils.

The MCP credential propagation feature adds two placeholders resolved from
the RLS contextvars (``current_auth_method`` + ``current_credential``):

* ``${USER_JWT}``      → raw JWT string when ``current_auth_method == "jwt"``,
  else empty string.
* ``${USER_API_KEY}``  → raw API key when ``current_auth_method == "api_key"``,
  else empty string.

``resolve_all_vars`` resolves BOTH ``os.environ`` vars AND the user-credential
placeholders in a single pass. When the contextvars are unset (no auth
context), both placeholders resolve to empty strings.
"""

import pytest

from src.infrastructure.database.rls_context import current_auth_method, current_credential
from src.infrastructure.env_utils import resolve_all_vars


class TestResolveUserJwt:
    """``${USER_JWT}`` resolution driven by ``current_auth_method`` + ``current_credential``."""

    def test_resolves_to_credential_when_method_jwt(self) -> None:
        # Arrange
        tok_m = current_auth_method.set("jwt")
        tok_c = current_credential.set("tok123")
        try:
            # Act
            result = resolve_all_vars("${USER_JWT}")
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        assert result == "tok123"

    def test_resolves_to_empty_when_method_api_key(self) -> None:
        # Arrange
        tok_m = current_auth_method.set("api_key")
        tok_c = current_credential.set("cpk_xyz")
        try:
            # Act
            result = resolve_all_vars("${USER_JWT}")
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        assert result == ""

    def test_resolves_to_empty_when_contextvars_unset(self) -> None:
        # Arrange — defaults
        assert current_auth_method.get() is None
        assert current_credential.get() is None

        # Act
        result = resolve_all_vars("${USER_JWT}")

        # Assert
        assert result == ""


class TestResolveUserApiKey:
    """``${USER_API_KEY}`` resolution."""

    def test_resolves_to_credential_when_method_api_key(self) -> None:
        # Arrange
        tok_m = current_auth_method.set("api_key")
        tok_c = current_credential.set("cpk_xyz")
        try:
            # Act
            result = resolve_all_vars("${USER_API_KEY}")
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        assert result == "cpk_xyz"

    def test_resolves_to_empty_when_method_jwt(self) -> None:
        # Arrange
        tok_m = current_auth_method.set("jwt")
        tok_c = current_credential.set("tok123")
        try:
            # Act
            result = resolve_all_vars("${USER_API_KEY}")
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        assert result == ""

    def test_resolves_to_empty_when_contextvars_unset(self) -> None:
        # Arrange — defaults
        assert current_auth_method.get() is None

        # Act
        result = resolve_all_vars("${USER_API_KEY}")

        # Assert
        assert result == ""


class TestResolveAllVarsMixed:
    """``resolve_all_vars`` resolves both os.environ and user-credential placeholders."""

    def test_resolves_os_env_and_user_jwt_together(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-abc")
        tok_m = current_auth_method.set("jwt")
        tok_c = current_credential.set("tok123")
        try:
            # Act
            result = resolve_all_vars("${OPENROUTER_API_KEY}/${USER_JWT}")
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        assert result == "or-abc/tok123"

    def test_resolves_os_env_and_user_api_key_together(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setenv("BASE_URL", "http://x")
        tok_m = current_auth_method.set("api_key")
        tok_c = current_credential.set("cpk_1")
        try:
            # Act
            result = resolve_all_vars("${BASE_URL}|${USER_API_KEY}")
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        assert result == "http://x|cpk_1"

    def test_bearer_prefix_with_user_jwt(self) -> None:
        # Arrange
        tok_m = current_auth_method.set("jwt")
        tok_c = current_credential.set("tok123")
        try:
            # Act
            result = resolve_all_vars("Bearer ${USER_JWT}")
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        assert result == "Bearer tok123"

    def test_bearer_prefix_with_user_api_key(self) -> None:
        # Arrange
        tok_m = current_auth_method.set("api_key")
        tok_c = current_credential.set("cpk_1")
        try:
            # Act
            result = resolve_all_vars("Bearer ${USER_API_KEY}")
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        assert result == "Bearer cpk_1"

    def test_all_contextvars_unset_yields_empty_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setenv("X", "ok")
        assert current_auth_method.get() is None

        # Act
        result = resolve_all_vars("${X}|${USER_JWT}|${USER_API_KEY}")

        # Assert
        assert result == "ok||"

    def test_plain_string_unchanged(self) -> None:
        # Act
        result = resolve_all_vars("plain-value")

        # Assert
        assert result == "plain-value"

    def test_empty_string_returns_empty(self) -> None:
        # Act
        result = resolve_all_vars("")

        # Assert
        assert result == ""
