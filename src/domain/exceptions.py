class DomainError(Exception):
    """Base domain exception."""

    pass


class ConfigError(DomainError):
    """Configuration error."""

    pass


class ConfigNotFoundError(ConfigError):
    """Configuration file not found."""

    pass


class ConfigValidationError(ConfigError):
    """Schema validation error."""

    def __init__(self, errors: list[dict]):
        self.errors = errors
        messages = [f"  - {e.get('loc', '?')}: {e.get('msg', '?')}" for e in errors]
        super().__init__("Validation errors:\n" + "\n".join(messages))


class ThreadNotFoundError(DomainError):
    """Thread not found."""

    pass


class AgentError(DomainError):
    """Agent execution error."""

    pass


class AgentNotFoundError(DomainError):
    """Agent not found."""

    pass


class AgentConfigAlreadyExistsError(DomainError):
    """Agent configuration already exists."""

    pass


class StorageError(DomainError):
    """Storage infrastructure error."""

    pass


class McpError(DomainError):
    """Base error for MCP operations."""

    pass


class McpConnectionError(McpError):
    """Error connecting to MCP server."""

    pass


class McpToolLoadError(McpError):
    """Error loading MCP tools."""

    pass
