"""Centralized error message templates.

The message text raised with every domain error is declared here so error
wording is discoverable, consistent and never duplicated. Callers format the
template with the runtime values::

    raise ConfigError(ErrorMessage.INVALID_AGENT_NAME.format(name))
"""

from enum import StrEnum
from string import Template


class ErrorMessage(StrEnum):
    """Catalog of centralized error message templates (``str.format`` style)."""

    # --- Configuration ---
    INVALID_AGENT_NAME = (
        "Invalid agent name '{name}'. Must match pattern: alphanumeric, "
        "dots, hyphens, underscores, 2-100 chars."
    )
    FILE_TOO_LARGE = "File too large. Maximum size is {max_size} bytes."
    FILE_NOT_UTF8 = "File must be valid UTF-8 encoded YAML."
    AGENT_NAME_MISMATCH = "Agent name in YAML '{yaml_name}' does not match provided name '{name}'"
    AGENT_NAME_MISMATCH_URL = "Agent name in YAML '{yaml_name}' does not match URL name '{name}'"
    YAML_INVALID = "Invalid YAML from {source}: {error}"
    YAML_NOT_MAPPING = "YAML from {source} must contain a YAML mapping, not {type}"
    YAML_VALIDATION_ERROR = "Validation error: {error}"
    YAML_EMPTY = "Empty YAML content from {source}"
    YAML_CONFIG_NOT_FOUND = "Config file not found: {path}"
    YAML_PROMPT_FILE_NOT_FOUND = "Prompt file not found: {path}"
    YAML_SYSTEM_PROMPT_FILE_DISALLOWED = (
        "system_prompt_file is not allowed in string-loaded YAML from {source}. "
        "Inline the prompt in system_prompt instead."
    )

    # --- Agent ---
    AGENT_NOT_FOUND = "Agent not found: {name}"
    AGENT_CONFIG_NOT_FOUND = "Agent config metadata not found: {name}"
    AGENT_CONFIG_NOT_FOUND_IN_STORE = "Agent config not found in store: {name}"
    AGENT_CONFIG_ALREADY_EXISTS = "Agent config already exists: {name}"
    AGENT_NO_FINAL_MESSAGES = "Graph completed but no messages were found in the final state."
    AGENT_EXECUTION_ERROR = "Agent execution error: {error}"
    AGENT_STREAMING_ERROR = "Streaming error: {error}"
    AGENT_HITL_APPROVE_ERROR = "HITL approve error: {error}"
    AGENT_HITL_REJECT_ERROR = "HITL reject error: {error}"
    AGENT_HITL_EDIT_ERROR = "HITL edit error: {error}"
    AGENT_STREAM_IDLE_TIMEOUT = (
        "Agent stream idle for {timeout}s (thread={thread_id}); aborting — a tool result "
        "was likely lost (flaky transport)."
    )
    AGENT_INVOKE_TIMEOUT = "Agent invoke timed out after {timeout}s (thread={thread_id})"

    # --- Thread ---
    THREAD_NOT_FOUND = "Thread not found: {thread_id}"
    THREAD_FAILED_CREATE = "Failed to create thread: {error}"
    THREAD_FAILED_GET = "Failed to get thread {thread_id}: {error}"
    THREAD_FAILED_LIST = "Failed to list threads: {error}"
    THREAD_FAILED_DELETE = "Failed to delete thread {thread_id}: {error}"
    THREAD_FAILED_ADD_MESSAGE = "Failed to add message to thread {thread_id}: {error}"

    # --- Storage / persistence ---
    STORAGE_REPO_NOT_INITIALIZED = "Thread repository not initialized. Check PostgreSQL connectivity."
    STORAGE_REGISTRY_NOT_INITIALIZED = "Agent registry not initialized. Check MinIO/PostgreSQL connectivity."
    STORAGE_PERSISTENCE_NOT_INITIALIZED = (
        "Persistence layer not initialized. Check MinIO/PostgreSQL connectivity."
    )
    STORAGE_FAILED_SAVE_AGENT_CONFIG = "Failed to save agent config metadata '{name}': {error}"
    STORAGE_FAILED_GET_AGENT_CONFIG = "Failed to get agent config metadata '{name}': {error}"
    STORAGE_FAILED_LIST_AGENT_CONFIG = "Failed to list agent config metadata: {error}"
    STORAGE_FAILED_DELETE_AGENT_CONFIG = "Failed to delete agent config metadata '{name}': {error}"
    STORAGE_FAILED_EXISTS_AGENT_CONFIG = "Failed to check existence of agent config '{name}': {error}"
    STORAGE_FAILED_PERSIST_STREAM = "Failed to persist AI message after stream: {error}"

    # --- HITL ---
    INVALID_HITL_ACTION = "Unsupported HITL action: {action}"

    # --- MCP ---
    MCP_CONNECTION_ERROR = "Failed to connect to MCP servers: {error}"
    MCP_TOOL_LOAD_ERROR = "Failed to load MCP tools: {error}"
    MCP_TOOL_CALL_TIMEOUT = "MCP tool '{name}' timed out after {timeout}s"

    # --- Prompt management ---
    PROMPT_MANAGER_NOT_INITIALIZED = "Prompt manager client not initialized"
    PROMPT_NOT_FOUND = "Prompt not found: {identifier}"
    PROMPT_ALREADY_EXISTS = "Prompt already exists: {identifier}"
    PROMPT_MANAGER_UNAVAILABLE = "Prompt manager unavailable during '{operation}' for '{identifier}': {error}"
    PROMPT_MANAGER_SERVER_ERROR = (
        "Prompt manager server error ({status_code}) during '{operation}' for '{identifier}'"
    )


def tmpl(template: str) -> Template:
    """Return a ``string.Template`` for ``$name`` style templates when needed."""
    return Template(template)
