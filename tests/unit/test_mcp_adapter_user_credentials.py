"""Tests for MCP credential propagation in :class:`LangchainMcpToolLoader`.

When an agent calls a remote MCP server (e.g. raganything), the outgoing
request should carry the CURRENT USER's credential instead of a static env-var
key. The loader resolves ``${USER_JWT}`` and ``${USER_API_KEY}`` placeholders
from the RLS contextvars. Empty resolved header values are DROPPED so a
JWT-authed request doesn't send an empty ``X-API-Key`` (and vice versa).

``MultiServerMCPClient`` is patched (external boundary) so no real MCP server
is contacted.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType
from src.infrastructure.database.rls_context import current_auth_method, current_credential
from src.infrastructure.mcp.adapter import LangchainMcpToolLoader


def _config(headers: dict[str, str]) -> McpServerConfig:
    return McpServerConfig(
        name="raganything",
        transport=McpTransportType.HTTP,
        url="http://raganything-api:8000/classical/mcp",
        headers=headers,
    )


class TestMcpUserCredentialPropagation:
    """``${USER_JWT}`` / ``${USER_API_KEY}`` resolved + empty headers dropped."""

    async def test_jwt_method_sends_bearer_and_drops_empty_api_key(self) -> None:
        # Arrange
        config = _config(
            {
                "Authorization": "Bearer ${USER_JWT}",
                "X-API-Key": "${USER_API_KEY}",
            }
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        tok_m = current_auth_method.set("jwt")
        tok_c = current_credential.set("tok123")
        try:
            # Act
            with patch(
                "src.infrastructure.mcp.adapter.MultiServerMCPClient",
                return_value=mock_client,
            ) as mock_cls:
                loader = LangchainMcpToolLoader()
                await loader.load_tools([config])
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert — Authorization resolved, X-API-Key dropped (empty)
        call_args = mock_cls.call_args[0][0]
        headers = call_args["raganything"]["headers"]
        assert headers == {"Authorization": "Bearer tok123"}

    async def test_api_key_method_sends_x_api_key_and_drops_empty_bearer(self) -> None:
        # Arrange
        config = _config(
            {
                "Authorization": "Bearer ${USER_JWT}",
                "X-API-Key": "${USER_API_KEY}",
            }
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        tok_m = current_auth_method.set("api_key")
        tok_c = current_credential.set("cpk_xyz")
        try:
            # Act
            with patch(
                "src.infrastructure.mcp.adapter.MultiServerMCPClient",
                return_value=mock_client,
            ) as mock_cls:
                loader = LangchainMcpToolLoader()
                await loader.load_tools([config])
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert — X-API-Key resolved, Authorization dropped (empty Bearer)
        call_args = mock_cls.call_args[0][0]
        headers = call_args["raganything"]["headers"]
        assert headers == {"X-API-Key": "cpk_xyz"}

    async def test_no_contextvar_drops_both_empty_headers(self) -> None:
        # Arrange
        config = _config(
            {
                "Authorization": "Bearer ${USER_JWT}",
                "X-API-Key": "${USER_API_KEY}",
            }
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        assert current_auth_method.get() is None

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            await loader.load_tools([config])

        # Assert — both headers dropped (empty)
        call_args = mock_cls.call_args[0][0]
        headers = call_args["raganything"]["headers"]
        assert headers == {}

    async def test_non_empty_static_header_preserved(self) -> None:
        # Arrange
        config = _config(
            {
                "Authorization": "Bearer ${USER_JWT}",
                "X-Custom-Header": "static-value",
            }
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        tok_m = current_auth_method.set("jwt")
        tok_c = current_credential.set("tok")
        try:
            # Act
            with patch(
                "src.infrastructure.mcp.adapter.MultiServerMCPClient",
                return_value=mock_client,
            ) as mock_cls:
                loader = LangchainMcpToolLoader()
                await loader.load_tools([config])
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert — static header preserved, Authorization resolved
        call_args = mock_cls.call_args[0][0]
        headers = call_args["raganything"]["headers"]
        assert headers == {"Authorization": "Bearer tok", "X-Custom-Header": "static-value"}

    async def test_os_env_var_still_resolved_alongside_user_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setenv("MCP_TIMEOUT", "30")
        config = _config(
            {
                "Authorization": "Bearer ${USER_JWT}",
                "X-Timeout": "${MCP_TIMEOUT}",
            }
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        tok_m = current_auth_method.set("jwt")
        tok_c = current_credential.set("jwt-tok")
        try:
            # Act
            with patch(
                "src.infrastructure.mcp.adapter.MultiServerMCPClient",
                return_value=mock_client,
            ) as mock_cls:
                loader = LangchainMcpToolLoader()
                await loader.load_tools([config])
        finally:
            current_auth_method.reset(tok_m)
            current_credential.reset(tok_c)

        # Assert
        call_args = mock_cls.call_args[0][0]
        headers = call_args["raganything"]["headers"]
        assert headers == {"Authorization": "Bearer jwt-tok", "X-Timeout": "30"}
