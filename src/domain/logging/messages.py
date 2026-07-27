"""Centralized log message templates.

All log message strings used across the application are declared here so they
are discoverable, non-duplicated, and easy to audit. Callers reference these
constants instead of inlining message text, e.g.::

    logger.info(LogMessage.AGENT_CONFIG_CREATED, agent_name)

Each template may contain ``%s``/``%d`` style placeholders consumed by the
stdlib logging lazy interpolation.
"""

from enum import StrEnum


class LogMessage(StrEnum):
    """Catalog of centralized log message templates (stdlib ``%`` style)."""

    # --- Application lifecycle ---
    APP_STARTUP_INITIATED = "Application startup initiated"
    APP_STARTUP_COMPLETE = "Application startup complete"
    APP_PERSISTENCE_INITIALIZED = "Persistence initialized"
    APP_PERSISTENCE_INIT_FAILED = "Failed to initialize persistence, falling back to filesystem registry"
    APP_SHUTDOWN_INITIATED = "Application shutdown initiated"
    APP_SHUTDOWN_COMPLETE = "Application shutdown complete"
    APP_PERSISTENCE_CLOSED = "Persistence closed"
    APP_PERSISTENCE_CLOSE_FAILED = "Error closing persistence"
    APP_MCP_LOADER_CLOSED = "MCP tool loader closed"
    APP_MCP_LOADER_CLOSE_FAILED = "Error closing MCP tool loader"
    APP_TRACING_SHUTDOWN = "Tracing provider shut down"
    APP_TRACING_SHUTDOWN_FAILED = "Error shutting down tracing provider"
    APP_MIGRATIONS_RUNNING = "Running database migrations..."
    APP_MIGRATIONS_DONE = "Database migrations completed"
    DEPENDENCIES_INITIALIZED = "Dependencies initialized"

    # --- Dependency wiring / persistence init ---
    TRACING_LANGFUSE_INIT = "Initializing Langfuse tracing provider (host=%s)"
    TRACING_PHOENIX_INIT = "Initializing Phoenix tracing provider (endpoint=%s)"
    TRACING_DISABLED = "Tracing disabled, using NoopTracingProvider"
    PERSISTENCE_INITIALIZING = "Initializing persistence layer"
    SQLALCHEMY_ENGINE_CREATED = (
        "SQLAlchemy async engine created (pool: AsyncAdaptedQueuePool, size=20, max_overflow=20)"
    )
    POSTGRES_REPOS_INITIALIZED = "PostgreSQL repositories initialized"
    MINIO_STORE_INITIALIZED = "MinIO store initialized (bucket=%s)"
    PERSISTENCE_REGISTRY_SET = "Persistence layer initialized, agent_registry set to PersistentAgentRegistry"
    PERSISTENT_REGISTRY_CLOSED = "Persistent registry closed"
    SQLALCHEMY_ENGINE_DISPOSED = "SQLAlchemy engine disposed"
    JWT_ADAPTER_CLOSED = "JWT adapter httpx client closed"
    PERSISTENCE_STORE_FILE_INITIALIZED = "Store file repository initialized (AsyncPostgresStore)"
    PERSISTENCE_STORE_FILE_INIT_FAILED = (
        "Failed to initialize store file repository with Postgres, falling back to InMemoryStore"
    )
    PERSISTENCE_STORE_FILE_FALLBACK_INMEMORY = "Store file repository initialized (InMemoryStore fallback)"

    # --- Agent config management ---
    AGENT_CONFIG_LISTED = "Listed %d agent configs"
    AGENT_CONFIG_LISTED_FROM_REPO = "Listed %d agent configs from repository"
    AGENT_CONFIG_GET = "Getting agent config: %s"
    AGENT_CONFIG_CREATING = "Creating agent config: %s"
    AGENT_CONFIG_CREATED = "Agent config created: %s"
    AGENT_CONFIG_CREATED_UC = "Created agent config '%s'"
    AGENT_CONFIG_UPDATING = "Updating agent config: %s"
    AGENT_CONFIG_UPDATED = "Agent config updated: %s"
    AGENT_CONFIG_UPDATED_UC = "Updated agent config '%s'"
    AGENT_CONFIG_DELETING = "Deleting agent config: %s"
    AGENT_CONFIG_DELETED = "Agent config deleted: %s"
    AGENT_CONFIG_DELETED_UC = "Deleted agent config '%s'"
    AGENT_CONFIG_METADATA_SAVED = "Saved agent config metadata '%s'"
    AGENT_CONFIG_METADATA_DELETED = "Deleted agent config metadata '%s'"
    AGENT_CONFIG_LOADED_FROM_STORE = "Loaded agent config '%s' from store"

    # --- Chat / messaging ---
    CHAT_RECEIVE = "[thread=%s] POST /chat - message=%s"
    CHAT_RESPONSE = "[thread=%s] Response status=%s content_len=%d"
    CHAT_STREAM_RECEIVE = "[thread=%s] POST /chat/stream - message=%s"
    CHAT_STREAM_COMPLETE = "[thread=%s] Stream complete, %d chunks"
    CHAT_STREAM_ERROR = "[thread=%s] Stream error after %d chunks"
    CHAT_SENDING = "Sending message to thread '%s' (agent=%s)"
    CHAT_SENT = "Chat completed [thread=%s][agent=%s] elapsed=%.2fs status=%s"
    CHAT_HITL = "HITL [thread=%s][agent=%s] elapsed=%.2fs status=%s"
    CHAT_SENDING_HUMAN = "[thread=%s][agent=%s] Sending human message"
    CHAT_SKIP_DUPLICATE_HUMAN = "[thread=%s] Skipping duplicate HUMAN message"
    CHAT_SENDING_HITL = "[thread=%s][agent=%s] Sending HITL decision (action=%s)"
    CHAT_STREAM_COMPLETE_UC = "Stream complete [thread=%s][agent=%s] %d chunks, elapsed=%.2fs, message=persisted"
    CHAT_STREAM_PERSIST_FAILED = "Failed to persist AI message after stream [thread=%s][agent=%s]"

    # --- Threads ---
    THREAD_CREATING = "Creating thread for agent=%s"
    THREAD_CREATED = "Thread created: id=%s agent=%s"
    THREAD_LISTED = "Listed %d threads"
    THREAD_GETTING = "Getting thread=%s"
    THREAD_DELETING = "Deleting thread=%s"
    THREAD_DELETED = "Thread deleted: %s"
    THREAD_MESSAGES_LISTED = "[thread=%s] Listed %d messages"

    # --- WebSocket ---
    WS_CONNECTED = "[thread=%s] WebSocket connected"
    WS_INVALID_JSON = "[thread=%s] Invalid JSON received: %s"
    WS_MESSAGE_RECEIVED = "[thread=%s] WS message received: %s"
    WS_STREAM_COMPLETE = "[thread=%s] WS stream complete, %d chunks"
    WS_STREAM_ERROR = "[thread=%s] WS stream error after %d chunks"
    WS_DISCONNECTED = "[thread=%s] WebSocket disconnected"
    WS_UNEXPECTED_ERROR = "[thread=%s] WebSocket unexpected error"

    # --- Prompt management ---
    PROMPT_CREATING = "Creating prompt: %s"
    PROMPT_CREATED = "Prompt created: %s"
    PROMPT_CREATED_SUCCESS = "Prompt created successfully: %s"
    PROMPT_UPDATING = "Updating prompt: %s"
    PROMPT_UPDATED = "Prompt updated: %s"
    PROMPT_UPDATED_SUCCESS = "Prompt updated successfully: %s"
    PROMPT_RETRIEVING = "Retrieving prompt: %s"
    PROMPT_RETRIEVING_CONTENT = "Retrieving prompt content: %s"
    PROMPT_RETRIEVED = "Retrieved prompt content for '%s' (version: %s, tags: %s)"
    PROMPT_CREATE_ERROR = "Error creating prompt '%s'"
    PROMPT_GET_ERROR = "Error getting prompt '%s'"
    PROMPT_GET_CONTENT_ERROR = "Error getting prompt content '%s'"
    PROMPT_UPDATE_ERROR = "Error updating prompt '%s'"
    PROMPT_TAG_ADDED = "Added tag '%s' to prompt '%s'"
    PROMPT_TAG_ADD_FAILED = "Failed to add tag '%s' to '%s': %s"
    PROMPT_PROVIDER_INITIALIZED = "Prompt provider initialized base_url=%s timeout=%ss"
    PROMPT_PROVIDER_INIT_FAILED = "Failed to initialize prompt provider client"
    PROMPT_DESC_UPDATE_UNSUPPORTED = (
        "Provider does not support updating description on existing prompts — description change ignored for '%s'"
    )

    # --- Validation warnings (Pydantic validators) ---
    VALIDATION_MSG_AND_HITL_EXCLUSIVE = "Provide either 'message' or HITL fields, not both"
    VALIDATION_ACTION_REQUIRED = "'action' is required for HITL decisions"
    VALIDATION_EDITS_REQUIRED = "'edits' is required for action 'edit'"
    VALIDATION_PROMPTS_MUTUALLY_EXCLUSIVE = "system_prompt and system_prompt_file are mutually exclusive"
    VALIDATION_COMMAND_REQUIRED = "'command' is required for stdio transport"
    VALIDATION_URL_REQUIRED = "'url' is required for http transport"

    # --- Infrastructure ---
    MCP_CONNECTING = "Connecting to MCP servers"
    MCP_TOOLS_LOADED = "Loaded %d MCP tools"
    MCP_TOOL_TIMEOUT = "MCP tool '%s' timed out after %ss"
    YAML_LOADED = "Loaded config from %s"
    DB_QUERY_FAILED = "Database operation failed: %s"

    # --- Chat use cases (send_message / stream_message) ---
    CHAT_INVOKE_COMPLETE = "[thread=%s][agent=%s] Invoke elapsed=%.2fs, status=%s, len=%d"
    CHAT_HITL_RECEIVED = "[thread=%s][agent=%s] HITL action=%s tool_call_id=%s"
    CHAT_HITL_COMPLETE = "[thread=%s][agent=%s] HITL elapsed=%.2fs, status=%s"
    CHAT_STREAM_STARTED = "[thread=%s][agent=%s] Stream started"
    CHAT_STREAM_ERROR_UC = "[thread=%s][agent=%s] Stream error after %d chunks"
    CHAT_STREAM_COMPLETE_PERSISTED = (
        "[thread=%s][agent=%s] Stream complete, %d chunks, elapsed=%.2fs, message=persisted"
    )

    # --- DeepAgent runner lifecycle ---
    AGENT_INVOKING = "[thread=%s] Invoking agent"
    AGENT_MESSAGE = "[thread=%s] Message: %s"
    AGENT_INVOKE_COMPLETE = "[thread=%s] Invoke complete, status=%s, elapsed=%.2fs"
    AGENT_EXECUTION_ERROR_LOG = "[thread=%s] Agent execution error"
    AGENT_FIRST_CHUNK = "[thread=%s] First chunk received, elapsed=%.2fs"
    AGENT_STREAMING = "[thread=%s] Streaming agent response"
    AGENT_STREAMING_ERROR_LOG = "[thread=%s] Streaming error"
    AGENT_STREAMING_WITH_MESSAGE = "[thread=%s] Streaming agent response with final message"
    AGENT_STREAM_WITH_MESSAGE_COMPLETE = "[thread=%s] Stream with message complete, %d chunks, elapsed=%.2fs, status=%s"
    AGENT_STREAM_COMPLETE = "[thread=%s] Stream complete, %d chunks, elapsed=%.2fs"
    AGENT_STREAM_IDLE_TIMEOUT = "[thread=%s] Agent stream idle timeout after %ss"
    AGENT_INVOKE_TIMEOUT = "[thread=%s] Agent invoke timeout after %ss"
    HITL_APPROVE = "[thread=%s] HITL approve"
    HITL_APPROVE_COMPLETE = "[thread=%s] HITL approve complete, elapsed=%.2fs"
    HITL_APPROVE_ERROR_LOG = "HITL approve error"
    HITL_REJECT = "[thread=%s] HITL reject, reason=%s"
    HITL_REJECT_COMPLETE = "[thread=%s] HITL reject complete, elapsed=%.2fs"
    HITL_REJECT_ERROR_LOG = "HITL reject error"
    HITL_EDIT = "[thread=%s] HITL edit, tool_call_id=%s"
    HITL_EDIT_COMPLETE = "[thread=%s] HITL edit complete, elapsed=%.2fs"
    HITL_EDIT_ERROR_LOG = "HITL edit error"

    # --- DeepAgent runner / ToolNode patching ---
    TOOLS_NODE_MISSING = "No 'tools' node found in graph; cannot patch handle_tool_errors"
    TOOLS_NODE_NO_BOUND = "'tools' node has no 'bound' attribute; cannot patch handle_tool_errors"
    TOOLNODE_PATCHED = "Patched ToolNode handle_tool_errors=True"
    TOOLNODE_PATCH_MISSING_ATTR = "ToolNode bound object missing _handle_tool_errors; patch not applied"
    STRUCTURED_RESPONSE_MISSING = "Structured response missing despite response_format being configured"
    STRUCTURED_RESPONSE_VALIDATION_FAILED = "Failed to validate structured_response against schema, returning raw data"
    STRUCTURED_FIELD_STRIPPED = "Stripped extra field from structured_response: '%s'"
    STRUCTURED_NESTED_FIELD_STRIPPED = "Stripped extra nested field: '%s.%s'"

    # --- Agent factory ---
    AGENT_CREATING = "Creating agent '%s' (model=%s)"
    AGENT_MCP_TOOLS_LOADING = "Loading MCP tools for agent '%s' (%d servers)"
    AGENT_MCP_TOOLS_LOADED = "Loaded %d MCP tools for agent '%s'"
    AGENT_TOOLS_TOTAL = "Agent '%s' tools: %d total"
    AGENT_SUBAGENTS = "Agent '%s' has %d subagents"
    AGENT_CREATE_ERROR = "Error creating agent '%s'"
    AGENT_CREATED = "Agent '%s' created successfully"
    TOOL_FORMAT_INVALID = "Invalid tool format '%s'"
    TOOL_MODULE_NOT_FOUND = "Module not found for tool '%s'"
    TOOL_ATTRIBUTE_NOT_FOUND = "Attribute '%s' not found in '%s'"
    SUBAGENT_PROMPT_LOAD_FAILED = (
        "Could not load system prompt for sub-agent '%s' from Phoenix, using YAML instructions if available."
    )

    # --- Persistent agent registry ---
    AGENT_CACHE_HIT = "Agent '%s' loaded from cache"
    AGENT_BUILDING = "Building agent '%s' from persistent store"
    AGENT_CACHED = "Agent '%s' ready and cached"
    AGENT_CACHE_INVALIDATED = "Invalidated cached agent '%s'"
    REGISTRY_CLOSING = "Closing persistent registry, clearing %d cached agents"

    # --- MinIO store ---
    MINIO_CONFIG_UPLOADED = "Uploaded agent config '%s' to MinIO bucket '%s'"
    MINIO_CONFIG_DELETED = "Deleted agent config '%s' from MinIO bucket '%s'"
    MINIO_BUCKET_EXISTS = "MinIO bucket '%s' already exists"
    MINIO_BUCKET_CREATED = "Created MinIO bucket '%s'"

    # --- MCP loader ---
    MCP_CONNECT_FAILED = "Failed to connect to MCP servers"
    MCP_TOOLS_LOAD_FAILED = "Failed to load MCP tools"

    # --- Phoenix prompt adapter ---
    PHOENIX_PROMPT_PROVIDER_INITIALIZED = "PhoenixPromptManagerProvider initialized base_url=%s timeout=%ss"
    PHOENIX_CLIENT_INIT_FAILED = "Failed to initialize Phoenix client"
    PROMPT_VERSION_CREATED = "Created prompt '%s'"
    PROMPT_VERSION_UPDATED = "Updated prompt '%s'"
    PROMPT_TAG_ADD_ERROR = "Error adding tag '%s' to '%s'"
    PHOENIX_DESC_UPDATE_UNSUPPORTED = (
        "Phoenix does not support updating description on existing prompts — description change ignored for '%s'"
    )

    # --- Phoenix tracing provider ---
    PHOENIX_PROVIDER_INIT = "Initializing PhoenixTracingProvider with endpoint=%s, project_name=%s"
    PHOENIX_TRACING_INITIALIZED = "Phoenix tracing initialized successfully"
    PHOENIX_SPANS_FLUSHED = "Flushed pending spans to Phoenix"
    PHOENIX_FLUSH_FAILED = "Error flushing spans to Phoenix"
    PHOENIX_TRACING_SHUTDOWN = "Phoenix tracing provider shutdown complete"
    TRACER_SHUTDOWN_FAILED = "Error shutting down tracer provider"

    # --- YAML config loader ---
    YAML_PARSE_FAILED = "Invalid YAML from %s"
    YAML_NOT_MAPPING_LOG = "YAML from %s must contain a YAML mapping, not %s"
    YAML_VALIDATION_FAILED = "Validation error from %s"
    CONFIG_FILE_NOT_FOUND_LOG = "Config file not found: %s"
    PROMPT_FILE_NOT_FOUND_LOG = "Prompt file not found: %s"
    YAML_EMPTY_LOG = "Empty YAML content from %s"
    YAML_SYSTEM_PROMPT_FILE_DISALLOWED = "system_prompt_file is not allowed in string-loaded YAML from %s"

    # --- Exception handler log lines (main.py) ---
    LOG_AGENT_CONFIG_ALREADY_EXISTS = "Agent config already exists: %s"
    LOG_STORAGE_ERROR = "Storage error: %s"
    LOG_AGENT_NOT_FOUND = "Agent not found: %s"
    LOG_CONFIG_NOT_FOUND = "Config not found: %s"
    LOG_THREAD_NOT_FOUND = "Thread not found: %s"
    LOG_PROMPT_NOT_FOUND = "Prompt not found: %s"
    LOG_PROMPT_ALREADY_EXISTS = "Prompt already exists: %s"
    LOG_PROMPT_MANAGER_UNAVAILABLE = "Prompt manager unavailable: %s"
    LOG_INVALID_HITL_ACTION = "Invalid HITL action: %s"
    LOG_CONFIG_VALIDATION_ERROR = "Config validation error: %s errors=%s"
    LOG_CONFIG_ERROR = "Config error: %s"
    LOG_AGENT_ERROR = "Agent error: %s"
    LOG_MCP_ERROR = "MCP error: %s"
    LOG_UNHANDLED_DOMAIN_ERROR = "Unhandled domain error: %s"

    # --- Security ---
    LOG_INVALID_API_KEY = "Invalid API key: %s"

    # --- Auth (dual JWT / API key) ---
    # The enum value is a stable prefix kept verbatim in the formatted log line
    # (no ``%s`` inside it) so tests can assert ``LogMessage.X in r.getMessage()``.
    # No PII is interpolated here — only error type / message for diagnostics.
    AUTH_JWT_DECODE_FAILED = "JWT decode failed"
    AUTH_JWKS_FETCH_FAILED = "JWKS fetch failed"
    AUTH_CREDENTIALS_VALIDATED = "Credentials validated for user_id=%s method=%s"

    # --- API key management (per-user) ---
    API_KEY_CREATED = "API key created: id=%s user_id=%s"
    API_KEY_REVOKED = "API key revoked: id=%s user_id=%s"
    API_KEY_LISTED = "Listed %d API keys for user_id=%s"

    # --- RLS (Row-Level Security) ---
    RLS_CONTEXT_SET = "RLS context set: app.user_id=%s"
    RLS_BYPASS_ENABLED = "RLS bypass enabled (row_security=off)"

    # --- LLM settings (per user) ---
    LLM_SETTINGS_DECRYPT_FAILED = "Failed to decrypt LLM API key for user_id=%s; returning masked=None"
    LLM_SETTINGS_REPO_INITIALIZED = "User LLM settings repository initialized"
    LLM_CRYPTO_KEY_EMPTY = (
        "SECRET_ENCRYPTION_KEY is empty — generated a throwaway in-memory Fernet key. "
        "Set SECRET_ENCRYPTION_KEY in production to persist encrypted API keys across restarts."
    )
