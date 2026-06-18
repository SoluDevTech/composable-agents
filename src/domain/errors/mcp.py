"""MCP (Model Context Protocol) domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class McpError(DomainError):
    """Base error for MCP operations."""

    status_code = ErrorCode.BAD_GATEWAY


class McpConnectionError(McpError):
    """Error connecting to an MCP server."""

    status_code = ErrorCode.BAD_GATEWAY


class McpToolLoadError(McpError):
    """Error loading MCP tools."""

    status_code = ErrorCode.BAD_GATEWAY
