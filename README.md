# composable-agents

Configure Deep Agent LangGraph agents in YAML and expose them via FastAPI.

**composable-agents** is a Python framework that lets you declare AI agents as YAML configurations and instantly expose them as a full-featured HTTP API. It is built on [deepagents](https://pypi.org/project/deepagents/) (LangGraph-based Deep Agent) with a strict hexagonal architecture, making every component testable and replaceable.

The server supports **multi-agent mode**: agents are created and managed via a REST API (backed by MinIO for YAML blob storage and PostgreSQL for metadata), each thread is bound to a specific agent at creation time, and agents are lazily instantiated on first use.

---

## Quickstart (5 minutes)

### Prerequisites

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) package manager
- PostgreSQL 15+ (required for thread and agent config persistence)
- MinIO (required for YAML config blob storage)
- An API key for at least one LLM provider (Anthropic, OpenAI, or Google)

### Installation

```bash
git clone https://github.com/your-org/composable-agents.git
cd composable-agents
uv sync
cp .env.example .env
```

Edit `.env` and add your API key and database credentials:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...
# or
GOOGLE_API_KEY=...

# PostgreSQL (required)
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=raganything
POSTGRES_PASSWORD=raganything
POSTGRES_DATABASE=raganything
```

### Create your first agent

Agents are created via the REST API by uploading a YAML configuration. A minimal agent only needs a name:

```yaml
name: my-agent
```

### Launch the server

```bash
uv run python -m src serve
```

The API starts on `http://localhost:8000`. On startup, the server:

1. **Runs Alembic migrations** automatically to bring the database schema up to date.
2. **Initializes persistence** (PostgreSQL engine, MinIO store, agent registry).

Agents are not loaded into memory until a thread references them for the first time.

### Test with curl

```bash
# Health check
curl http://localhost:8000/health

# Create an agent by uploading a YAML file
curl -X POST http://localhost:8000/api/v1/agents \
  -F "agent_name=my-agent" \
  -F "file=@my-agent.yaml"

# Create a thread bound to the agent
curl -X POST http://localhost:8000/api/v1/threads \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "my-agent"}'

# Send a message (replace <thread_id> with the id from the previous response)
curl -X POST http://localhost:8000/api/v1/chat/<thread_id> \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what can you do?"}'
```

---

## Multi-Agent Architecture

composable-agents supports running **multiple agents simultaneously**. Each agent is defined by a YAML configuration stored in MinIO, with metadata tracked in PostgreSQL.

### How it works

1. **Agent creation** -- Agents are created via `POST /api/v1/agents` by uploading a YAML file. The configuration is stored in MinIO, and metadata is saved to PostgreSQL.
2. **Thread creation** -- When creating a thread via `POST /api/v1/threads`, you specify an `agent_name`. If no matching agent exists in the registry, the API returns `404`.
3. **Lazy loading** -- The agent (LangGraph graph + runner) is created only when a thread first sends a message to it. Subsequent requests reuse the cached runner.
4. **Per-thread binding** -- Each thread is permanently bound to its agent. Different threads can use different agents.

### Key components

| Component | Location | Role |
|---|---|---|
| `AgentRegistry` (port) | `src/domain/ports/agent_registry.py` | Abstract interface for retrieving agent runners by name. |
| `PersistentAgentRegistry` (adapter) | `src/infrastructure/persistent_registry/adapter.py` | MinIO + PostgreSQL backed registry, creates and caches runners on demand. |
| `AgentNotFoundError` | `src/domain/exceptions.py` | Raised when a requested agent name has no corresponding config. |

### Example: two agents, two threads

```bash
# Create the research-assistant agent
curl -X POST http://localhost:8000/api/v1/agents \
  -F "agent_name=research-assistant" \
  -F "file=@research-assistant.yaml"

# Create the code-reviewer agent
curl -X POST http://localhost:8000/api/v1/agents \
  -F "agent_name=code-reviewer" \
  -F "file=@code-reviewer.yaml"

# Create a thread using the research assistant agent
curl -X POST http://localhost:8000/api/v1/threads \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "research-assistant"}'
# Returns: {"id": "thread-1-uuid", "agent_name": "research-assistant", ...}

# Create another thread using the code reviewer agent
curl -X POST http://localhost:8000/api/v1/threads \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "code-reviewer"}'
# Returns: {"id": "thread-2-uuid", "agent_name": "code-reviewer", ...}

# Each thread talks to its own agent
curl -X POST http://localhost:8000/api/v1/chat/<thread-1-uuid> \
  -H "Content-Type: application/json" \
  -d '{"message": "Summarize the latest research on transformers."}'

curl -X POST http://localhost:8000/api/v1/chat/<thread-2-uuid> \
  -H "Content-Type: application/json" \
  -d '{"message": "Review this Python function for security issues."}'
```

---

## Configuration YAML Reference

Every agent is defined by a single YAML file validated against the `AgentConfig` Pydantic schema.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` (required) | -- | Unique agent name (1-100 characters). |
| `model` | `string` | `"claude-sonnet-4-5-20250929"` | LLM model identifier. See [Supported Models](#supported-models). |
| `system_prompt` | `string` | `null` | Inline system prompt. Use this for all agents created via the REST API. |
| `system_prompt_file` | `string` | `null` | Path to a text file containing the system prompt (only works with filesystem-based loading; **rejected** by the persistent MinIO-backed registry -- inline the prompt in `system_prompt` instead). Mutually exclusive with `system_prompt`. |
| `tools` | `list[string]` | `[]` | Python tool references in `module.path:attribute` format. |
| `middleware` | `list[MiddlewareType]` | `[]` | Middleware to attach. See [Middlewares](#middlewares). |
| `backend` | `BackendConfig` | `{"type": "state"}` | Persistence backend. See [Backends](#backends). |
| `hitl` | `HITLConfig` | `{"rules": {}}` | Human-in-the-loop interrupt rules. |
| `memory` | `list[string]` | `[]` | Paths to memory files (e.g. `"./AGENTS.md"`). |
| `skills` | `list[string]` | `[]` | Paths to skill directories (e.g. `"./skills/"`). |
| `subagents` | `list[SubAgentConfig]` | `[]` | Sub-agent definitions for delegation. |
| `mcp_servers` | `list[McpServerConfig]` | `[]` | MCP server connections. See [MCP Servers](#mcp-servers). |
| `debug` | `bool` | `false` | Enable debug mode. |

### SubAgentConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` (required) | -- | Sub-agent name. |
| `description` | `string` (required) | -- | Description of the sub-agent's role. |
| `instructions` | `string` | `null` | System prompt / instructions for the sub-agent. |
| `model` | `string` | `null` | Override model for this sub-agent. |
| `tools` | `list[string]` | `[]` | Tool references specific to this sub-agent. |
| `skills` | `list[string]` | `[]` | Skill paths for this sub-agent. |
| `mcp_servers` | `list[McpServerConfig]` | `[]` | MCP servers for this sub-agent. |

### McpServerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` (required) | -- | Server identifier. |
| `transport` | `"stdio"` or `"http"` (required) | -- | Transport type. |
| `command` | `string` | `null` | Command to run (required for `stdio` transport). |
| `args` | `list[string]` | `[]` | Command arguments (for `stdio` transport). |
| `url` | `string` | `null` | Server URL (required for `http` transport). |
| `headers` | `dict[string, string]` | `{}` | HTTP headers (for `http` transport). |
| `env` | `dict[string, string]` | `{}` | Environment variables for the server process. Supports `${VAR_NAME}` syntax for resolving env vars. |

### HITL Rules

HITL rules map tool names to either a boolean or a detailed rule:

```yaml
hitl:
  rules:
    write_file: true                  # Simple: interrupt on any call
    execute:                          # Detailed: restrict allowed decisions
      allowed_decisions:
        - approve
        - reject
```

Allowed decisions: `approve`, `edit`, `reject`.

---

## Supported Models

| Provider | Format | Example |
|---|---|---|
| Anthropic | `claude-<variant>` | `claude-sonnet-4-5-20250929` |
| OpenAI | `openai:<model>` | `openai:gpt-4o` |
| Google | `google_genai:<model>` | `google_genai:gemini-2.0-flash` |

The default model is `claude-sonnet-4-5-20250929`.

For OpenAI-compatible endpoints (OpenRouter, LiteLLM, vLLM, etc.), set the `OPENAI_BASE_URL` environment variable to point to your endpoint. The OpenAI SDK reads this variable automatically.

---

## MCP Servers

Agents can connect to [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) servers for tool access. MCP servers are defined in the agent's YAML config:

```yaml
name: mcp-agent
model: claude-sonnet-4-5-20250929
system_prompt: "You are an agent with MCP tool access."
mcp_servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

Environment variables in `env` fields support the `${VAR_NAME}` resolution syntax.

---

## Middlewares

| Name | Enum Value | Description |
|---|---|---|
| Todo List | `todo_list` | Filesystem-based task tracking middleware. |
| Filesystem | `filesystem` | Gives the agent read/write access to files on disk. |
| Sub-Agent | `sub_agent` | Enables delegation to sub-agents defined in `subagents`. |

---

## Backends

| Name | Enum Value | Description |
|---|---|---|
| State | `state` | Default in-memory state backend (no extra config). |
| Filesystem | `filesystem` | Persists agent state to a directory. Accepts `root_dir`. |
| Store | `store` | LangGraph store-based backend. |
| Composite | `composite` | Reserved for advanced composite configurations. |

Example with a filesystem backend:

```yaml
backend:
  type: filesystem
  root_dir: "./workspace"
```

---

## API Reference

All endpoints are prefixed appropriately. The server runs on `http://localhost:8000` by default.

| Method | Path | Description | Success Status |
|---|---|---|---|
| `GET` | `/health` | Health check | `200` |
| `POST` | `/api/v1/agents` | Create a new agent (upload YAML via multipart form) | `201` |
| `GET` | `/api/v1/agents` | List all agent config metadata | `200` |
| `GET` | `/api/v1/agents/{agent_name}` | Get a specific agent configuration | `200` |
| `PUT` | `/api/v1/agents/{agent_name}` | Update an existing agent (upload YAML via multipart form) | `200` |
| `DELETE` | `/api/v1/agents/{agent_name}` | Delete an agent configuration | `204` |
| `POST` | `/api/v1/threads` | Create a new conversation thread (bound to an agent) | `201` |
| `GET` | `/api/v1/threads` | List all threads | `200` |
| `GET` | `/api/v1/threads/{thread_id}` | Get a specific thread | `200` |
| `DELETE` | `/api/v1/threads/{thread_id}` | Delete a thread | `204` |
| `GET` | `/api/v1/threads/{thread_id}/messages` | List messages in a thread | `200` |
| `POST` | `/api/v1/chat/{thread_id}` | Send a message and get the full response | `200` |
| `POST` | `/api/v1/chat/{thread_id}/stream` | Send a message and stream the response (SSE) | `200` |
| `POST` | `/api/v1/threads/{thread_id}/hitl` | Submit a human-in-the-loop decision | `200` |
| `WS` | `/api/v1/ws/{thread_id}` | WebSocket endpoint for streaming chat | -- |

### Error Responses

| Status | Condition |
|---|---|
| `400` | General configuration error, invalid agent name, file too large |
| `404` | Thread not found, agent not found, or config not found |
| `409` | Agent config already exists (on create) |
| `422` | Validation error (bad request body, invalid config schema) |
| `502` | Agent execution error (LLM failure) |
| `500` | Unexpected domain error |
| `503` | Storage error (MinIO or PostgreSQL unavailable) |

---

## curl Examples

### 1. Health Check

```bash
curl http://localhost:8000/health
```

Response:

```json
{"status": "ok"}
```

### 2. Create an Agent

Upload a YAML configuration file to create a new agent:

```bash
curl -X POST http://localhost:8000/api/v1/agents \
  -F "agent_name=example-agent" \
  -F "file=@example-agent.yaml"
```

Response (`201`):

```json
{
  "name": "example-agent",
  "model": "openai:anthropic/claude-haiku-4.5:nitro",
  "system_prompt": "You are a helpful assistant.",
  "system_prompt_file": null,
  "tools": [],
  "middleware": [],
  "backend": {"type": "state", "root_dir": null},
  "hitl": {"rules": {}},
  "memory": [],
  "skills": [],
  "subagents": [],
  "mcp_servers": [],
  "debug": false
}
```

### 3. List Available Agents

```bash
curl http://localhost:8000/api/v1/agents
```

Response (`200`):

```json
[
  {
    "name": "code-reviewer",
    "created_at": "2025-01-15T10:00:00.000000",
    "updated_at": "2025-01-15T10:00:00.000000"
  },
  {
    "name": "example-agent",
    "created_at": "2025-01-15T10:05:00.000000",
    "updated_at": "2025-01-15T10:05:00.000000"
  }
]
```

### 4. Get a Specific Agent Configuration

```bash
curl http://localhost:8000/api/v1/agents/example-agent
```

Response (`200`):

```json
{
  "name": "example-agent",
  "model": "openai:anthropic/claude-haiku-4.5:nitro",
  "system_prompt": "You are a helpful assistant.",
  "system_prompt_file": null,
  "tools": [],
  "middleware": [],
  "backend": {"type": "state", "root_dir": null},
  "hitl": {"rules": {}},
  "memory": [],
  "skills": [],
  "subagents": [],
  "mcp_servers": [],
  "debug": false
}
```

If the agent does not exist:

```bash
curl http://localhost:8000/api/v1/agents/nonexistent
```

Response (`404`):

```json
{"detail": "Agent introuvable: nonexistent"}
```

### 5. Update an Agent

Upload a new YAML file to replace an existing agent's configuration:

```bash
curl -X PUT http://localhost:8000/api/v1/agents/example-agent \
  -F "file=@example-agent-v2.yaml"
```

Response (`200`): returns the updated `AgentConfig`.

### 6. Delete an Agent

```bash
curl -X DELETE http://localhost:8000/api/v1/agents/example-agent
```

Response: `204 No Content`

### 7. Create a Thread

The `agent_name` must match an existing agent in the persistent registry (created via `POST /api/v1/agents`).

```bash
curl -X POST http://localhost:8000/api/v1/threads \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "example-agent"}'
```

Response (`201`):

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "agent_name": "example-agent",
  "messages": [],
  "created_at": "2025-01-15T10:30:00.000000",
  "updated_at": "2025-01-15T10:30:00.000000"
}
```

If the agent name does not match any registered agent:

```bash
curl -X POST http://localhost:8000/api/v1/threads \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "nonexistent-agent"}'
```

Response (`404`):

```json
{"detail": "Agent introuvable: nonexistent-agent"}
```

### 8. Send a Message

```bash
curl -X POST http://localhost:8000/api/v1/chat/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain the hexagonal architecture pattern in 3 sentences."}'
```

Response (`200`):

```json
{
  "role": "ai",
  "content": "Hexagonal architecture separates core business logic from external concerns...",
  "timestamp": "2025-01-15T10:30:05.000000",
  "tool_calls": null,
  "tool_call_id": null
}
```

### 9. Stream a Message (SSE)

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/a1b2c3d4-e5f6-7890-abcd-ef1234567890/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Write a haiku about programming."}'
```

Response (Server-Sent Events):

```
data: Lines
data:  of
data:  code
data:  align
data: ...
```

### 10. List All Threads

```bash
curl http://localhost:8000/api/v1/threads
```

Response (`200`):

```json
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "agent_name": "example-agent",
    "messages": [],
    "created_at": "2025-01-15T10:30:00.000000",
    "updated_at": "2025-01-15T10:30:00.000000"
  },
  {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "agent_name": "research-assistant",
    "messages": [],
    "created_at": "2025-01-15T10:31:00.000000",
    "updated_at": "2025-01-15T10:31:00.000000"
  }
]
```

### 11. Get a Specific Thread

```bash
curl http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 12. List Messages in a Thread

```bash
curl http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890/messages
```

Response (`200`):

```json
[
  {
    "role": "human",
    "content": "Explain the hexagonal architecture pattern in 3 sentences.",
    "timestamp": "2025-01-15T10:30:00.000000",
    "tool_calls": null,
    "tool_call_id": null
  },
  {
    "role": "ai",
    "content": "Hexagonal architecture separates core business logic from external concerns...",
    "timestamp": "2025-01-15T10:30:05.000000",
    "tool_calls": null,
    "tool_call_id": null
  }
]
```

### 13. HITL -- Approve a Pending Tool Call

When the agent is configured with HITL rules and a tool call is interrupted, submit a decision:

```bash
curl -X POST http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890/hitl \
  -H "Content-Type: application/json" \
  -d '{
    "tool_call_id": "call_abc123",
    "action": "approve"
  }'
```

Response (`200`):

```json
{
  "role": "ai",
  "content": "Action approved. Proceeding with file write.",
  "timestamp": "2025-01-15T10:31:00.000000",
  "tool_calls": null,
  "tool_call_id": null
}
```

### 14. HITL -- Reject a Pending Tool Call

```bash
curl -X POST http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890/hitl \
  -H "Content-Type: application/json" \
  -d '{
    "tool_call_id": "call_abc123",
    "action": "reject",
    "reason": "This operation is too risky for production."
  }'
```

### 15. HITL -- Edit and Approve a Pending Tool Call

```bash
curl -X POST http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890/hitl \
  -H "Content-Type: application/json" \
  -d '{
    "tool_call_id": "call_abc123",
    "action": "edit",
    "edits": {"filename": "safe_output.txt", "content": "sanitized content"}
  }'
```

### 16. Delete a Thread

```bash
curl -X DELETE http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Response: `204 No Content`

### WebSocket

Connect to the WebSocket endpoint and send JSON messages:

```javascript
const ws = new WebSocket("ws://localhost:8000/api/v1/ws/<thread_id>");
ws.onopen = () => ws.send(JSON.stringify({ message: "Hello" }));
ws.onmessage = (event) => {
  if (event.data === "[END]") {
    console.log("Response complete");
  } else {
    process.stdout.write(event.data);
  }
};
```

---

## Architecture

composable-agents follows a strict **hexagonal architecture** (ports and adapters). The domain layer has zero dependencies on frameworks or infrastructure.

```
                    +---------------------------+
                    |      HTTP / WebSocket     |
                    |   (FastAPI application)   |
                    +------------+--------------+
                                 |
                    +------------+--------------+
                    |       Use Cases           |
                    | (application/use_cases/)  |
                    +------+----------+---------+
                           |          |
               +-----------+          +-----------+
               |                                  |
    +----------+---------+            +-----------+---------+
    |   Domain Ports     |            |   Domain Entities   |
    | (abstract classes) |            | AgentConfig, Thread |
    +----------+---------+            |   Message           |
               |                      +---------------------+
    +----------+---------+
    |  Infrastructure    |
    | (adapters)         |
    +--------------------+
    | - DeepAgentRunner  |
    | - PersistentRegistry|
    | - YamlConfigLoader |
    | - MinioConfigStore |
    | - PostgresThreads  |
    | - Alembic (migrate)|
    +--------------------+
```

### File Tree

```
composable-agents/
  src/
    main.py                            # FastAPI app creation and lifespan (runs migrations)
    config.py                          # Pydantic Settings (env vars, database_url property)
    dependencies.py                    # Dependency injection wiring
    alembic.ini                        # Alembic configuration
    alembic/
      env.py                           # Alembic env (async engine, model imports)
      versions/
        001_create_agent_configs_table.py
        002_create_threads_and_messages_tables.py
    application/
      requests/
        chat.py                        # Request models (ChatRequest, CreateThreadRequest, HITLDecisionRequest)
      routes/
        health.py                      # GET /health
        threads.py                     # CRUD /api/v1/threads
        chat.py                        # POST /api/v1/chat/{id} and /stream
        agents.py                      # CRUD /api/v1/agents (create, list, get, update, delete)
        websocket.py                   # WS /api/v1/ws/{id}
      use_cases/
        send_message.py                # Invoke agent synchronously
        stream_message.py              # Stream agent response
        create_agent_config.py         # Create agent config (MinIO + Postgres)
        update_agent_config.py         # Update agent config
        delete_agent_config.py         # Delete agent config
        get_agent_config.py            # Get agent config from MinIO
        list_agent_configs.py          # List agent configs from Postgres
        thread_management.py           # Create / get / list / delete threads
    domain/
      entities/
        agent_config.py                # AgentConfig, BackendConfig, HITLConfig, SubAgentConfig
        agent_config_metadata.py       # AgentConfigMetadata
        mcp_server_config.py           # McpServerConfig, McpTransportType
        message.py                     # Message (role, content, timestamp, tool_calls)
        thread.py                      # Thread (id, agent_name, messages, timestamps)
        tracing_config.py              # TracingConfig, TracingProviderType
      ports/
        agent_config_loader.py         # Abstract: load config from file or string
        agent_config_repository.py     # Abstract: CRUD for agent config metadata
        agent_config_store.py          # Abstract: object storage for YAML blobs
        agent_registry.py              # Abstract: get_runner(name), list_agents(), close()
        agent_runner.py                # Abstract: invoke, stream, HITL operations
        mcp_tool_loader.py             # Abstract: load MCP tools
        thread_repository.py           # Abstract: CRUD for threads
        tracing_provider.py            # Abstract: tracing lifecycle
      exceptions.py                    # DomainError hierarchy (incl. AgentNotFoundError, StorageError)
    infrastructure/
      env_utils.py                     # ${VAR_NAME} environment variable resolution
      database/
        models/
          base.py                      # SQLAlchemy DeclarativeBase
          agent_config.py              # AgentConfigModel (ORM)
          thread.py                    # ThreadModel + MessageModel (ORM)
      deepagent/
        adapter.py                     # DeepAgentRunner (LangGraph adapter)
        factory.py                     # create_agent_from_config (resolves tools, middleware, backend)
        example_tools.py               # Example tools: current_time, word_count
      mcp/
        adapter.py                     # LangchainMcpToolLoader
      minio_store/
        adapter.py                     # MinioAgentConfigStore (YAML blob storage)
      persistent_registry/
        adapter.py                     # PersistentAgentRegistry (MinIO + Postgres backed)
      postgres_repository/
        adapter.py                     # PostgresAgentConfigRepository
      postgres_thread/
        adapter.py                     # PostgresThreadRepository (thread persistence)
        models.py                      # Re-exports ThreadModel, MessageModel
      yaml_config/
        adapter.py                     # YamlAgentConfigLoader
      tracing/
        langfuse_adapter.py            # Langfuse tracing provider
        phoenix_adapter.py             # Phoenix tracing provider
        noop_adapter.py                # No-op tracing provider (default)
  tests/
    conftest.py
    fixtures/
      external.py                      # External service fixtures
      in_memory_thread_repository.py   # In-memory thread repository for tests
    unit/
      test_agent_config.py
      test_agent_crud.py
      test_deep_agent_runner.py
      test_env_utils.py
      test_factory.py
      test_factory_mcp_integration.py
      test_langfuse_adapter.py
      test_mcp_adapter.py
      test_mcp_lifecycle.py
      test_mcp_server_config.py
      test_message.py
      test_minio_store.py
      test_noop_tracing.py
      test_persistent_registry.py
      test_phoenix_adapter.py
      test_postgres_repository.py
      test_postgres_thread_repository.py
      test_routes.py
      test_runner_tracing.py
      test_send_message.py
      test_thread.py
      test_thread_management.py
      test_tracing_config.py
      test_tracing_di.py
      test_tracing_lifecycle.py
      test_yaml_loader.py
  .env.example                         # Environment variable template
  Dockerfile                           # Container image
  pyproject.toml                       # Project metadata and dependencies
  CONTRIBUTING.md                      # Contributor guide
  uv.lock                             # Lockfile
```

---

## Examples

Below are example YAML configurations you can upload via `POST /api/v1/agents`. Save each to a file and use `curl -F "agent_name=..." -F "file=@your-file.yaml"`.

### Minimal Agent

The simplest possible agent. Uses all defaults (Claude Sonnet, no tools, state backend).

```yaml
name: minimal-agent
```

### Example Agent (OpenAI-compatible endpoint)

A basic agent using an OpenAI-compatible model via OpenRouter.

```yaml
name: example-agent
model: "openai:anthropic/claude-haiku-4.5:nitro"
system_prompt: "You are a helpful assistant."
```

### MCP Agent

An agent connected to an MCP filesystem server.

```yaml
name: mcp-agent
model: claude-sonnet-4-5-20250929
system_prompt: "You are an agent with MCP tool access."
mcp_servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

### Research Assistant with Tools

An agent with custom tools and filesystem persistence.

```yaml
name: research-assistant
model: "claude-sonnet-4-5-20250929"
system_prompt: |
  You are a research assistant specialized in technical documentation.
  Always cite your sources and provide structured summaries.
tools:
  - "src.infrastructure.deepagent.example_tools:current_time"
  - "src.infrastructure.deepagent.example_tools:word_count"
middleware:
  - filesystem
backend:
  type: filesystem
  root_dir: "./workspace"
debug: false
```

### Code Reviewer with HITL and Subagents

A multi-agent system with human-in-the-loop approval.

```yaml
name: code-reviewer
model: "claude-sonnet-4-5-20250929"
system_prompt: |
  You are an expert code reviewer. Analyze code for correctness,
  performance, security, and maintainability.
middleware:
  - filesystem
  - sub_agent
backend:
  type: state
hitl:
  rules:
    write_file: true
    execute:
      allowed_decisions:
        - approve
        - reject
subagents:
  - name: security-auditor
    description: "Specialized in security vulnerability analysis"
    instructions: "Focus on OWASP Top 10 and common security patterns"
  - name: performance-analyst
    description: "Specialized in performance optimization"
    instructions: "Analyze time complexity, memory usage, and bottlenecks"
```

---

## Database (PostgreSQL)

Thread and agent config persistence is backed by PostgreSQL, accessed via SQLAlchemy's async ORM (`asyncpg` driver).

### Schema

The database uses a flat normalized schema with two tables for thread persistence:

| Table | Description |
|---|---|
| `threads` | One row per conversation thread. Columns: `id` (PK, VARCHAR 36), `agent_name`, `created_at`, `updated_at`. |
| `messages` | One row per message. Columns: `id` (PK), `thread_id` (FK to `threads.id`, CASCADE delete), `role`, `content`, `timestamp`, `tool_calls` (JSONB), `status`, `structured_response` (JSONB). |

Indexes: `ix_messages_thread_id`, `ix_messages_thread_id_timestamp`, `ix_threads_agent_name`.

A third table, `agent_configs`, stores agent configuration metadata.

### Migrations (Alembic)

Alembic migrations live in `src/alembic/versions/` and run **automatically at startup** (via `asyncio.to_thread()` in the FastAPI lifespan). You never need to run `alembic upgrade` manually in normal operation.

To create a new migration manually:

```bash
cd src
uv run alembic revision -m "describe_your_change"
```

To run migrations manually (useful for debugging):

```bash
cd src
uv run alembic upgrade head
```

To check current migration status:

```bash
cd src
uv run alembic current
```

### Architecture Decisions

- **Hexagonal architecture**: `ThreadRepository` (port) -> `PostgresThreadRepository` (adapter). The domain layer has no knowledge of SQLAlchemy.
- **Session-per-method**: Each repository method creates its own `AsyncSession` from the engine, ensuring thread-safety for concurrent FastAPI requests.
- **Connection pooling**: `AsyncAdaptedQueuePool` with `pool_size=20`, `max_overflow=20`, and `pool_pre_ping=True`.
- **Cascade deletes**: Deleting a thread automatically deletes all its messages via `ON DELETE CASCADE` at both the SQL and ORM level.
- **Message ordering**: Messages are sorted by `timestamp` (oldest first). The ORM relationship specifies `order_by`, and the adapter applies a defensive Python sort as well.
- **JSONB columns**: `tool_calls` and `structured_response` are stored as PostgreSQL `JSONB`, allowing structured data without additional join tables.

---

## Environment Variables

Configured via `.env` file or environment variables. See `.env.example`.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | -- | API key for Anthropic models. |
| `OPENAI_API_KEY` | -- | API key for OpenAI models. |
| `GOOGLE_API_KEY` | -- | API key for Google models. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible endpoints. Set to use OpenRouter, LiteLLM, vLLM, etc. |
| `HOST` | `0.0.0.0` | Server bind host. |
| `PORT` | `8000` | Server bind port. |

### PostgreSQL Variables

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | PostgreSQL server hostname. |
| `POSTGRES_PORT` | `5433` | PostgreSQL server port. |
| `POSTGRES_USER` | `raganything` | Database user. |
| `POSTGRES_PASSWORD` | `raganything` | Database password. |
| `POSTGRES_DATABASE` | `raganything` | Database name. |

The async connection URL is built automatically as `postgresql+asyncpg://<user>:<password>@<host>:<port>/<database>`.

### MinIO Variables

| Variable | Default | Description |
|---|---|---|
| `MINIO_ENDPOINT` | `localhost:9040` | MinIO server endpoint. |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key. |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key. |
| `MINIO_BUCKET` | `composable-agents` | Bucket for YAML config blob storage. |
| `MINIO_SECURE` | `false` | Use HTTPS for MinIO connections. |

### Tracing Variables

| Variable | Default | Description |
|---|---|---|
| `TRACING_PROVIDER` | `none` | Tracing backend: `none`, `langfuse`, or `phoenix`. |
| `TRACING_ENABLED` | `false` | Enable/disable tracing. |
| `TRACING_PROJECT_NAME` | `composable-agents` | Project name for the tracing backend. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse server URL. |
| `LANGFUSE_PUBLIC_KEY` | -- | Langfuse public key. |
| `LANGFUSE_SECRET_KEY` | -- | Langfuse secret key. |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006` | Phoenix collector endpoint. |
| `PHOENIX_API_KEY` | -- | Phoenix API key. |
| `LANGCHAIN_API_KEY` | -- | LangChain/LangSmith API key. |
| `LANGCHAIN_PROJECT` | `composable-agents` | LangChain/LangSmith project name. |

---

## Development

### Install dependencies (including dev tools)

```bash
uv sync
```

### Run the test suite

```bash
uv run pytest tests/ -v
```

### Run tests with coverage

```bash
uv run pytest tests/ -v --cov=src
```

### Lint

```bash
uv run ruff check .
```

### Type check

```bash
uv run mypy src/
```

---

## Optional Dependencies

The project provides optional dependency groups for tracing support:

```bash
# Langfuse tracing only
uv sync --extra langfuse

# Phoenix tracing only
uv sync --extra phoenix

# All tracing providers
uv sync --extra tracing
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on:

- Project architecture and dependency rules
- How to add custom tools, middlewares, and backends
- How the YAML schema works
- Running tests and linting
- Code style conventions

---

## License

This project does not currently include a license file. Contact the maintainers for licensing information.
