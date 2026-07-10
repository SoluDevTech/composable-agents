# composable-agents

Configure Deep Agent LangGraph agents in YAML and expose them via FastAPI.

**composable-agents** is a Python framework that lets you declare AI agents as simple YAML files and instantly expose them as a full-featured HTTP API. It is built on [deepagents](https://pypi.org/project/deepagents/) (LangGraph-based Deep Agent) with a strict hexagonal architecture, making every component testable and replaceable.

The server supports **multi-agent mode**: multiple agents are defined as separate YAML files in an `agents/` directory, each thread is bound to a specific agent at creation time, and agents are lazily instantiated on first use.

---

## Quickstart (5 minutes)

### Prerequisites

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) package manager
- PostgreSQL 15+ (required for thread and agent config persistence)
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
OPENAI_API_KEY=sk-...

# PostgreSQL (required)
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=raganything
POSTGRES_PASSWORD=raganything
POSTGRES_DATABASE=raganything
```

### Configure your agents

Each agent is a standalone YAML file inside the `agents/` directory. A minimal agent only needs a name. Create `agents/my-agent.yaml`:

```yaml
name: my-agent
```

Or use one of the provided examples in the `agents/` directory (see [Examples](#examples)).

### Validate the configuration

```bash
uv run python -m src validate agents/my-agent.yaml
```

### Launch the server

```bash
uv run python -m src.main serve
```

The API starts on `http://localhost:8000`. On startup, the server:

1. **Runs Alembic migrations** automatically to bring the database schema up to date.
2. **Initializes persistence** (PostgreSQL engine, MinIO store, agent seeding).
3. Reads the `AGENTS_DIR` environment variable (default: `./agents`) to discover available agents.

Agents are not loaded into memory until a thread references them for the first time.

### Test with curl

```bash
# Health check
curl http://localhost:8000/health

# Create a thread bound to an agent (agent_name must match a YAML filename in agents/)
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

composable-agents now supports running **multiple agents simultaneously**. Each agent is defined by a separate YAML file in the `agents/` directory.

### How it works

1. **Discovery** -- On startup, the server scans `AGENTS_DIR` (default: `./agents`) for `.yaml` files. The filename (without extension) becomes the agent name.
2. **Thread creation** -- When creating a thread via `POST /api/v1/threads`, you specify an `agent_name`. If no matching YAML file exists, the API returns `404`.
3. **Lazy loading** -- The agent (LangGraph graph + runner) is created only when a thread first sends a message to it. Subsequent requests reuse the cached runner.
4. **Per-thread binding** -- Each thread is permanently bound to its agent. Different threads can use different agents.

### Key components

| Component | Location | Role |
|---|---|---|
| `AgentRegistry` (port) | `src/domain/ports/agent_registry.py` | Abstract interface for retrieving agent runners by name. |
| `DeepAgentRegistry` (adapter) | `src/infrastructure/deepagent/registry.py` | Scans `agents/` directory, creates and caches runners on demand. |
| `AgentNotFoundError` | `src/domain/exceptions.py` | Raised when a requested agent name has no corresponding YAML file. |

### Example: two agents, two threads

```bash
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
| `system_prompt` | `string` | `null` | Inline system prompt. Mutually exclusive with `system_prompt_file`. |
| `system_prompt_file` | `string` | `null` | Path to a text file containing the system prompt (resolved relative to the YAML file). Mutually exclusive with `system_prompt`. |
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

### Authenticating to MCP servers with API keys

When an MCP server requires authentication via a custom HTTP header (e.g. `X-API-Key`), use the `headers` field. The `${VAR_NAME}` syntax is supported for resolving environment variables at runtime:

```yaml
mcp_servers:
  - name: bricks
    transport: http
    url: https://raganything.soludev.tech/bricks/mcp
    headers:
      X-API-Key: "${MCP_RAGANYTHING_API_KEY}"
```

Set the corresponding environment variable in `.env`:

```dotenv
MCP_RAGANYTHING_API_KEY=your-shared-secret-key
```

The value must match the `API_KEY` configured on the [mcp-raganything](https://github.com/soludev/mcp-raganything) server.

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
| `POST` | `/api/v1/threads` | Create a new conversation thread (bound to an agent) | `201` |
| `GET` | `/api/v1/threads` | List all threads | `200` |
| `GET` | `/api/v1/threads/{thread_id}` | Get a specific thread | `200` |
| `DELETE` | `/api/v1/threads/{thread_id}` | Delete a thread | `204` |
| `GET` | `/api/v1/threads/{thread_id}/messages` | List messages in a thread | `200` |
| `POST` | `/api/v1/chat/{thread_id}` | Send a message and get the full response | `200` |
| `POST` | `/api/v1/chat/{thread_id}/stream` | Send a message and stream the response (SSE) | `200` |
| `POST` | `/api/v1/threads/{thread_id}/hitl` | Submit a human-in-the-loop decision | `200` |
| `GET` | `/api/v1/agents` | List all agent configs from `agents/` directory | `200` |
| `GET` | `/api/v1/agents/{agent_name}` | Get a specific agent configuration | `200` |
| `WS` | `/api/v1/ws/{thread_id}` | WebSocket endpoint for streaming chat | -- |
| `POST` | `/prompts/create` | Create a new prompt | `201` |
| `GET` | `/prompts/get/{identifier}` | Get a specific prompt by identifier, version, or tag | `200` |
| `PUT` | `/prompts/update/{identifier}` | Update an existing prompt (creates new version) | `200` |

### Error Responses

| Status | Condition |
|---|---|
| `400` | General configuration error |
| `404` | Thread not found, agent not found, or config file not found |
| `422` | Validation error (bad request body, invalid config schema) |
| `502` | Agent execution error (LLM failure) |
| `500` | Unexpected domain error |

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

### 2. List Available Agents

```bash
curl http://localhost:8000/api/v1/agents
```

Response (`200`):

```json
[
  {
    "name": "code-reviewer",
    "model": "claude-sonnet-4-5-20250929",
    "system_prompt": "You are an expert code reviewer...",
    "tools": [],
    "middleware": ["filesystem", "sub_agent"],
    "backend": {"type": "state", "root_dir": null},
    "hitl": {"rules": {"write_file": true, "execute": {"allowed_decisions": ["approve", "reject"]}}},
    "subagents": [...]
  },
  {
    "name": "example-agent",
    "model": "openai:anthropic/claude-haiku-4.5:nitro",
    "system_prompt": "You are a helpful assistant.",
    "tools": [],
    "middleware": [],
    "backend": {"type": "state", "root_dir": null},
    "hitl": {"rules": {}},
    "subagents": []
  }
]
```

### 3. Get a Specific Agent Configuration

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
{"detail": "Fichier de configuration introuvable: agents/nonexistent.yaml"}
```

### 4. Create a Thread

The `agent_name` must match an existing YAML filename (without the `.yaml` extension) in the `agents/` directory.

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

If the agent name does not match any YAML file:

```bash
curl -X POST http://localhost:8000/api/v1/threads \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "nonexistent-agent"}'
```

Response (`404`):

```json
{"detail": "Agent introuvable: nonexistent-agent"}
```

### 5. Send a Message

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

### 6. Stream a Message (SSE)

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/a1b2c3d4-e5f6-7890-abcd-ef1234567890/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Write a haiku about programming."}'
```

Response (Server-Sent Events):

```
data: {"type":"thinking","data":"Hmm, a haiku needs 5-7-5 syllables..."}

data: {"type":"content","data":"Lines"}

data: {"type":"content","data":" of"}

data: {"type":"content","data":" code"}

data: {"type":"content","data":" align"}

data: {"type":"content","data":"..."}

data: {"type":"message","data":"{\"role\":\"ai\",\"content\":\"Lines of code align...\",\"timestamp\":\"2025-04-24T10:30:05.000000Z\",\"tool_calls\":null,\"status\":\"completed\",\"structured_response\":null,\"thinking\":\"Hmm, a haiku needs 5-7-5 syllables...\"}"}

data: [DONE]
```

The stream emits **typed `StreamEvent` JSON objects** over SSE:

| `type` | Description | Persisted? |
|---|---|---|
| `thinking` | Reasoning / chain-of-thought tokens from extended-thinking models (e.g., Claude reasoning). | Yes — saved in `Message.thinking` |
| `content` | Response text / markdown tokens as they are generated. | Yes — aggregated into `Message.content` |
| `message` | The final complete `Message` JSON with all fields (`role`, `content`, `timestamp`, `tool_calls`, `status`, `structured_response`, `thinking`). Identical in format to the synchronous `POST /chat/{thread_id}` response. | Yes — persisted as the AI turn in the thread |

The stream ends with `data: [DONE]`.

This design prevents Cloudflare timeout issues (~100s on idle connections) because chunks and SSE pings (every 15s) keep the connection active. Clients can switch rendering based on `type`:

- Render `thinking` events in a collapsible reasoning panel.
- Append `content` events directly to the chat bubble.
- Wait for the `message` event to finalize metadata (status, structure, tool calls).

### 7. List All Threads

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

### 8. Get a Specific Thread

```bash
curl http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 9. List Messages in a Thread

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

### 10. HITL -- Approve a Pending Tool Call

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

### 11. HITL -- Reject a Pending Tool Call

```bash
curl -X POST http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890/hitl \
  -H "Content-Type: application/json" \
  -d '{
    "tool_call_id": "call_abc123",
    "action": "reject",
    "reason": "This operation is too risky for production."
  }'
```

### 12. HITL -- Edit and Approve a Pending Tool Call

```bash
curl -X POST http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890/hitl \
  -H "Content-Type: application/json" \
  -d '{
    "tool_call_id": "call_abc123",
    "action": "edit",
    "edits": {"filename": "safe_output.txt", "content": "sanitized content"}
  }'
```

### 13. Delete a Thread

```bash
curl -X DELETE http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Response: `204 No Content`

### 14. Prompt Management

Prompts are managed via a dedicated registry backed by Phoenix. Enable prompt management by setting `TRACING_PROVIDER=phoenix` and `PHOENIX_PROMPT_ENABLED=true` in your `.env`.

#### 14.1 Create a Prompt

```bash
curl -X POST http://localhost:8000/prompts/create \
  -H "Content-Type: application/json" \
  -d '{
    "identifier": "customer-support",
    "content": [
      {
        "role": "system",
        "content": "You are a helpful customer support agent. Be polite and professional."
      }
    ],
    "model_name": "claude-sonnet-4-5-20250929",
    "description": "Prompt for general customer support queries",
    "tags": ["production"],
    "metadata": {"project_name": "composable-agents", "agent_type": "deep_agent"}
  }'
```

Response (`200`):

```json
{
  "status": "success",
  "prompt": {
    "identifier": "customer-support",
    "description": "Prompt for general customer support queries",
    "current_version": {
      "version_id": "v1",
      "content": [...],
      "model_name": "claude-sonnet-4-5-20250929",
      "created_at": "2025-01-15T10:30:00.000000",
      "tags": ["support", "production"]
    },
    "created_at": "2025-01-15T10:30:00.000000",
    "updated_at": "2025-01-15T10:30:00.000000"
  }
}
```

#### 14.2 List All Prompts

```bash
curl http://localhost:8000/prompts/customer-support
```

Optional query parameters:
- `version_id`: Get a specific version
- `tag`: Get the prompt with a specific tag

Response (`200`):

```json
{
    "status": "success",
    "prompt": {
        "identifier": "customer-support",
        "description": "",
        "current_version": {
            "version_id": "UHJvbXB0VmVyc2lvbjo4Mw==",
            "content": [
                {
                    "role": "system",
                    "content": "You are a helpful customer support agent. Be polite and professional."
                }
            ],
            "model_name": "claude-sonnet-4-5-20250929",
            "tags": []
        },
        "created_at": null,
        "updated_at": null
    }
}
```

#### 14.3 Update a Prompt

Create a new version of an existing prompt:

```bash
curl -X PUT http://localhost:8000/prompts/update/customer-support \
  -H "Content-Type: application/json" \
  -d '{
    "content": [
      {
        "role": "system",
        "content": "You are a knowledgeable customer support agent. Be polite, professional, and thorough in your responses."
      }
    ],
    "model_name": "claude-sonnet-4-5-20250929",
    "description": "Updated prompt for customer support (more detailed)",
    "tags": ["production"],
    "metadata": {"project_name": "composable-agents", "agent_type": "deep_agent"}
  }'
```

Response (`200`):

```json
{
  "status": "success",
  "prompt": {
    "identifier": "customer-support",
    "description": "Updated prompt for customer support (more detailed)",
    "current_version": {
      "version_id": "v2",
      "content": [...],
      "model_name": "claude-sonnet-4-5-20250929",
      "created_at": "2025-01-15T10:31:00.000000",
      "tags": ["support", "production"]
    }
  },
  "message": "Prompt 'customer-support' updated successfully"
}
```

### WebSocket

Connect to the WebSocket endpoint and send JSON messages:

```javascript
const ws = new WebSocket("ws://localhost:8000/api/v1/ws/<thread_id>");
ws.onopen = () => ws.send(JSON.stringify({ message: "Hello" }));
ws.onmessage = (event) => {
  if (event.data === "[END]") {
    console.log("Response complete");
    return;
  }
  const data = JSON.parse(event.data);
  switch (data.type) {
    case "thinking": console.log("[Thinking]", data.data); break;
    case "content":  process.stdout.write(data.data); break;
    case "message":  console.log("Final message:", data.data); break;
  }
};
```

The WebSocket stream emits typed `StreamEvent` JSON objects: `thinking` (reasoning tokens), `content` (response text), `message` (final full `Message` JSON), then `[END]`.

---

## Prompt Management Setup

To enable prompt management in Phoenix:

### 1. Install Optional Dependencies

```bash
uv sync --extra phoenix
```

Or add to `pyproject.toml`:
```toml
arize-phoenix-otel = ">=0.1.0"
openinference-instrumentation-langchain = ">=0.1.0"
httpx = ">=0.27.0"
```

### 2. Configure Environment Variables

Add to `.env`:

```dotenv
PROVIDER=phoenix
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006
PHOENIX_PROMPT_ENABLED=true
PHOENIX_API_KEY=your-api-key-here
```

### 3. Architecture

Prompt management follows the **Clean Architecture** pattern:

- **Domain Entity** (`src/domain/entities/prompt.py`): `Prompt`, `PromptVersion`
- **Domain Port** (`src/domain/ports/prompt_manager.py`): `PromptManager` interface
- **Use Cases** (`src/application/use_cases/`): `CreatePromptUseCase`, `GetPromptUseCase`, `GetPromptContentUseCase`, `UpdatePromptUseCase`
- **Request DTOs** (`src/application/requests/prompt.py`): Request models for each endpoint
- **Response DTOs** (`src/application/responses/prompt.py`): `PromptResponse`, `PromptVersionResponse`
- **Routes** (`src/application/routes/prompt.py`): FastAPI endpoint handlers
- **Infrastructure Adapter** (`src/infrastructure/prompt_management/adapter.py`): Phoenix REST API implementation

All prompt management operations are async and fully integrated with the FastAPI dependency injection system.

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
    | - DeepAgentRegistry|
    | - YamlConfigLoader |
    | - PostgresThreads  |
    | - Alembic (migrate)|
    +--------------------+
```

### File Tree

```
composable-agents/
  agents/                              # YAML agent configuration files
    example-agent.yaml                 #   Basic example agent
    minimal.yaml                       #   Minimal agent (name only)
    mcp-agent.yaml                     #   Agent with MCP server tools
    research-assistant.yaml            #   Research assistant with tools
    code-reviewer.yaml                 #   Code reviewer with HITL + subagents
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
        agents.py                      # GET /api/v1/agents
        websocket.py                   # WS /api/v1/ws/{id}
      use_cases/
        send_message.py                # Invoke agent synchronously
        stream_message.py              # Stream agent response
        create_agent_config.py         # Create agent config (MinIO + Postgres)
        update_agent_config.py         # Update agent config
        delete_agent_config.py         # Delete agent config
        get_agent_config.py            # Get agent config from MinIO
        list_agent_configs.py          # List agent configs from Postgres
        load_agent_config.py           # Load and validate a YAML config
        seed_agents.py                 # Seed built-in agents from agents/ dir
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
        agent_config_loader.py         # Abstract: load config from file
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
        registry.py                    # DeepAgentRegistry (lazy loading + caching from agents/ dir)
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
      test_load_agent_config_use_case.py
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
      test_registry.py
      test_routes.py
      test_runner_tracing.py
      test_seed_agents.py
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

### Minimal Agent

`agents/minimal.yaml` -- the simplest possible agent. Uses all defaults (Claude Sonnet, no tools, state backend).

```yaml
name: minimal-agent
```

### Example Agent (OpenAI-compatible endpoint)

`agents/example-agent.yaml` -- a basic agent using an OpenAI-compatible model via OpenRouter.

```yaml
name: example-agent
model: "openai:anthropic/claude-haiku-4.5:nitro"
system_prompt: "You are a helpful assistant."
```

### MCP Agent

`agents/mcp-agent.yaml` -- an agent connected to an MCP filesystem server.

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

`agents/research-assistant.yaml` -- an agent with custom tools and filesystem persistence.

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

`agents/code-reviewer.yaml` -- a multi-agent system with human-in-the-loop approval.

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
| `AGENTS_DIR` | `./agents` | Directory containing agent YAML configuration files. |
| `OPENAI_API_KEY` | -- | API key for OpenAI models. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible endpoints. Set to use OpenRouter, LiteLLM, vLLM, etc. |
| `HOST` | `0.0.0.0` | Server bind host. |
| `PORT` | `8000` | Server bind port. |
| `MCP_RAGANYTHING_API_KEY` | -- | Shared API key for authenticating to mcp-raganything MCP servers. Must match the `API_KEY` set on the raganything server. |

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
| `TRACING_PROJECT_NAME` | `composable-agents` | Project name for the tracing backend. |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006` | Phoenix collector endpoint. |
| `PHOENIX_API_KEY` | -- | Phoenix API key. |

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

### Validate all agent YAML files

```bash
for f in agents/*.yaml; do uv run python -m src validate "$f"; done
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

## Deployment on Railway

[Railway](https://railway.app/) is a deployment platform that supports Docker-based services with managed PostgreSQL.

### Architecture on Railway

```
Railway project
├── PostgreSQL (Railway managed plugin)
├── composable-agents (Dockerfile deploy)
└── (mcp-raganything — separate Railway service or project)
```

### Step-by-step

1. **Create a Railway project** and add a PostgreSQL plugin.

2. **Deploy composable-agents**:
   - New Service → GitHub Repo → select this repository.
   - Railway detects the `Dockerfile` automatically.
   - Set the port to `8000`.

3. **Deploy mcp-raganything** (separate Railway service or project):
   - See the [mcp-raganything README](https://github.com/soludev/mcp-raganything#deployment-on-railway) for Railway deployment instructions.
   - Note the generated public domain (e.g. `mcp-raganything-production.up.railway.app`).

4. **Configure environment variables** in the Railway dashboard:

   | Variable | Example | Notes |
   |----------|---------|-------|
   | `OPENAI_API_KEY` | `sk-...` | OpenAI API key |
   | `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint |
   | `POSTGRES_HOST` | `roundhouse.proxy.rlwy.net` | Railway PostgreSQL host |
   | `POSTGRES_PORT` | `33019` | Railway PostgreSQL port (not 5432) |
   | `POSTGRES_USER` | `postgres` | Railway PostgreSQL user |
   | `POSTGRES_PASSWORD` | `********` | Railway PostgreSQL password |
   | `POSTGRES_DATABASE` | `railway` | Railway PostgreSQL database name |
   | `AGENTS_DIR` | `./agents` | Directory containing agent YAML configs |
   | `MCP_RAGANYTHING_API_KEY` | `your-shared-secret` | Must match `API_KEY` on mcp-raganything |
   | `TRACING_PROVIDER` | `phoenix` | Tracing backend: `none`, `langfuse`, or `phoenix` |
   | `PHOENIX_COLLECTOR_ENDPOINT` | `https://phoenix.xxx.railway.app` | Phoenix collector URL |

5. **Update agent YAML configs** to point MCP server URLs to the Railway-deployed mcp-raganything domain:

   ```yaml
   mcp_servers:
     - name: bricks
       transport: http
       url: https://mcp-raganything-production.up.railway.app/bricks/mcp
       headers:
         X-API-Key: "${MCP_RAGANYTHING_API_KEY}"
   ```

   The `${MCP_RAGANYTHING_API_KEY}` placeholder is resolved from the environment variable at runtime.

6. **MinIO** (optional — only if using MinIO for agent config storage):
   - Deploy MinIO as a separate Railway service or use an external S3-compatible service.
   - Set `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET` accordingly.

7. **Verify deployment**:

   ```bash
   curl https://composable-agents-production.up.railway.app/health
   ```

### Notes

- Railway automatically generates a public domain for each service.
- The `agents/` directory is baked into the Docker image at build time. To update agent configs without redeploying, use MinIO-backed agent config storage (see `AGENTS_DIR` and MinIO variables).
- Alembic migrations run automatically on startup.

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
