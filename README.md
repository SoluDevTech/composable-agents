# composable-agents

Configure Deep Agent LangGraph agents in YAML and expose them via FastAPI.

**composable-agents** is a Python framework that lets you declare AI agents as simple YAML files and instantly expose them as a full-featured HTTP API. It is built on [deepagents](https://pypi.org/project/deepagents/) (LangGraph-based Deep Agent) with a strict hexagonal architecture, making every component testable and replaceable.

The server supports **multi-agent mode**: multiple agents are defined as separate YAML files in an `agents/` directory, each thread is bound to a specific agent at creation time, and agents are lazily instantiated on first use. Sub-agents declared in the `subagents` config are fully traced: every event emitted by a sub-agent carries its name in the `source` field of the corresponding `TraceEvent`, so the client can group events per sub-agent (see [TraceEvent](#traceevent-format)).

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
DATABASE_URL=postgresql://raganything:raganything@localhost:5433/raganything
```

> **⚠️ Breaking change:** The `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DATABASE` environment variables have been replaced by a single `DATABASE_URL` variable. If you are upgrading from a previous version, construct your `DATABASE_URL` as `postgresql://<user>:<password>@<host>:<port>/<database>` and remove the old `POSTGRES_*` variables from your `.env`.

> **⚠️ Breaking change (trace events):** The legacy `StreamEvent` SSE format and the `messages` table have been removed. The `/stream` and WebSocket endpoints now emit `TraceEvent` JSON objects. See [Breaking Changes](#breaking-changes) for migration details.

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

# Stream a message (yields TraceEvent JSON objects, one per SSE line, ends with [DONE])
curl -N -X POST http://localhost:8000/api/v1/chat/<thread_id>/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what can you do?"}'

# Get the full thread history (thread + turns grouped by turn_id)
curl http://localhost:8000/api/v1/threads/<thread_id>/history

# Get the flat trace of events for a thread
curl http://localhost:8000/api/v1/threads/<thread_id>/trace
```

---

## Multi-Agent Architecture

composable-agents now supports running **multiple agents simultaneously**. Each agent is defined by a separate YAML file in the `agents/` directory. Sub-agents declared via `subagents` are traced individually: each `TraceEvent` they emit includes the sub-agent name in its `source` field, so the timeline can be grouped per sub-agent on the client side.

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
| `description` | `string` | `null` | Optional human-readable description of the agent (max 500 characters). Stored in the `agent_configs` table and exposed via `AgentConfigMetadata`. |
| `model` | `string` | `"claude-sonnet-4-5-20250929"` | LLM model identifier. See [Supported Models](#supported-models). |
| `system_prompt` | `string` | `null` | Inline system prompt. Mutually exclusive with `system_prompt_file`. |
| `system_prompt_file` | `string` | `null` | Path to a text file containing the system prompt (resolved relative to the YAML file). Mutually exclusive with `system_prompt`. |
| `tools` | `list[string]` | `[]` | Python tool references in `module.path:attribute` format. |
| `backend` | `BackendConfig` | `{"type": "state", "store_backend": "memory", "checkpoint_backend": "memory"}` | Persistence backend. See [Backends](#backends). |
| `hitl` | `HITLConfig` | `{"rules": {}}` | Human-in-the-loop interrupt rules. |
| `memory` | `list[string]` | `[]` | Paths to memory files (e.g. `"./AGENTS.md"`). |
| `skills` | `list[string]` | `[]` | Paths to skill directories (e.g. `"./skills/"`). |
| `subagents` | `list[SubAgentConfig]` | `[]` | Sub-agent definitions for delegation. |
| `mcp_servers` | `list[McpServerConfig]` | `[]` | MCP server connections. See [MCP Servers](#mcp-servers). |
| `debug` | `bool` | `false` | Enable debug mode. |
| `response_format` | `dict` | `null` | Inline JSON Schema dict for structured output. See [Structured Output (response_format)](#structured-output-response_format). |

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
| `agent_ref` | `string` | `null` | Name of an existing agent to reference. When set, the backend resolves the referenced agent's `model`, `system_prompt`, `mcp_servers`, `tools`, and `response_format` at runner-build time. Explicit values on the `SubAgentConfig` override the referenced agent's values. See [Agent references (`agent_ref`)](#agent-references-agent_ref). |

### Agent references (`agent_ref`)

A `SubAgentConfig` can reference another existing agent by name via the `agent_ref` field. This lets you compose agents without duplicating their configuration.

**Resolution rules:**

- At runner-build time, the backend looks up the referenced agent's `AgentConfig` and copies its `model`, `system_prompt`, `mcp_servers`, `tools`, and `response_format` into the sub-agent.
- Any field set explicitly on the `SubAgentConfig` (e.g. `model`, `instructions`) **overrides** the value inherited from the referenced agent.
- **One level only** — the referenced agent's own `subagents` are ignored. References are not resolved recursively.

**Validation (enforced at create/update time):**

- **Self-reference** (`agent_ref` equal to the parent agent's `name`) is rejected with a `ConfigError`.
- **Non-existent reference** (`agent_ref` pointing to an agent that does not exist) is rejected with a `ConfigError`.

**Cache invalidation:**

When an agent is updated or deleted, the registry also invalidates any agents that reference it via `agent_ref` in their `subagents`. This ensures stale runners are rebuilt on next use.

Example:

```yaml
name: orchestrator
subagents:
  - name: researcher
    agent_ref: research-assistant   # inherits model, system_prompt, mcp_servers, tools, response_format
    instructions: "Focus on recent papers."  # overrides system_prompt
```

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

## Structured Output (`response_format`)

The `response_format` field in agent YAML configures structured output — forcing the LLM to reply with JSON conforming to a JSON Schema. Define it inline as a dict (a valid JSON Schema) in the agent's YAML:

```yaml
name: invoice-extractor
model: claude-sonnet-4-5-20250929
response_format:
  type: object
  properties:
    invoice_number: { type: string }
    total_cents: { type: integer }
    currency: { type: string, enum: ["USD", "EUR", "GBP"] }
    paid: { anyOf: [{ type: boolean }, { type: "null" }] }
  required: [invoice_number, total_cents, currency]
  additionalProperties: false
```

### Native passthrough to deepagents/langchain

The dict is passed **natively** to `create_deep_agent(response_format=dict)`. No custom tool injection or prompt instruction concatenation is performed — the previous "tool leurre" hack (`_create_response_tool`, `_JSON_TYPE_MAP`, `STRUCTURED_OUTPUT_INSTRUCTION`) has been deleted.

langchain uses an **`AutoStrategy`** internally to pick the right delivery mechanism based on the model name:

- **`ProviderStrategy`** — the schema is passed as a native provider parameter (Anthropic `response_format`/tool_use strict mode, OpenAI `response_format` with `json_schema`, etc.).
- **`ToolStrategy`** — when the provider does not support native structured output, langchain injects a real tool whose schema is the JSON Schema, and the LLM is asked to call it.

You do not need to choose the strategy yourself — `AutoStrategy` selects based on the configured `model`.

### `structured_response` delivery

When the LLM produces a structured response, it is attached to the `Message` as `structured_response` (a dict validated against the schema). The `AI_MESSAGE` trace event carries the structured payload **inside `content`** as a JSON-serialized `Message` — it is **not** placed in `metadata`. The `metadata` of an `AI_MESSAGE` now only contains `{"status": ...}`.

Clients consuming `AI_MESSAGE` events must JSON-parse `content` and read `structured_response` from the resulting `Message` object.

### Missing structured response

If the LLM fails to produce a structured response despite a `response_format` being configured:

- A warning is logged (`STRUCTURED_RESPONSE_MISSING`).
- `Message.structured_response` is set to `None`.
- **No error is raised** — the client decides how to handle the absence.

### Supported JSON Schema constructs

`schema_utils.py` converts the JSON Schema dict to a Pydantic model at agent build time. The converter supports:

- `type` (string, integer, number, boolean, object, array, string)
- `type: ["string", "null"]` — array form for nullable scalars
- `anyOf` — nullable fields (use `anyOf: [{type: <T>}, {type: "null"}]`)
- `enum` — maps to `Literal` on the Pydantic side
- `properties` / `required` — nested objects
- `items` — arrays of objects or scalars

Not supported (will raise at build time or be ignored):

- `$ref`, `$defs`
- `oneOf`, `allOf`
- `if` / `then` / `else`
- `dependentSchemas`
- `patternProperties`

### Provider strict-mode constraints

When `AutoStrategy` selects `ProviderStrategy` against a provider that enforces strict mode (e.g. Anthropic's strict tool-use), the schema must satisfy the provider's constraints or the request will be rejected:

- Set `additionalProperties: false` on every object (recommended default).
- Use `anyOf` for nullable fields — do not use `type: ["string", "null"]` for Anthropic strict mode; use `anyOf: [{type: "string"}, {type: "null"}]` instead.
- Do **not** put `default` on `required` fields (Anthropic strict mode forbids it).
- All properties listed in `required` must appear in `properties`.

These constraints only apply when the provider enforces strict mode; `ToolStrategy` is more permissive. Since `AutoStrategy` picks automatically, authoring schemas that satisfy the strict constraints up front is the safest approach.

---


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

> **Registry migration:** The MCP server **registry** (CRUD API, OpenAPI→MCP generation, Swagger 2.0 conversion, Fernet encryption, mounter, startup rehydration) used to live in this brick. It has been **moved to [mcp-raganything](https://github.com/soludev/mcp-raganything)**, which now owns the `/api/v1/mcp/servers` REST surface. composable-agents no longer ships the registry routes, use cases, repository, OpenAPI factory, Swagger 2.0 converter, Fernet cipher, or mounter.
>
> **Schema ownership stays here:** composable-agents remains the owner of the `mcp_servers` PostgreSQL table schema. The table is created and evolved by this brick's Alembic migrations (`008_create_mcp_servers_table`, `009_alter_mcp_servers_add_openapi`). mcp-raganything is a **consumer** of the shared table and assumes the schema has already been applied — its `McpRegistryStore` no longer self-creates the table. On a fresh database, composable-agents' migrations must run before the mcp-raganything registry is used.
>
> What remains in this brick is:
>
> - `McpServerConfig` — the entity used by agent YAML to declare an MCP server connection.
> - `McpToolLoader` (port) / `LangchainMcpToolLoader` (adapter) — loads tools from an MCP server **by URL** at agent build time. The URLs come from the agent YAML directly, or from entries registered in mcp-raganything's registry (which composable-agents reads via its UI/backend when needed).
> - `McpConnectionError` / `McpToolLoadError` — domain errors raised when an MCP server cannot be reached or its tools fail to load.
>
> `SECRET_ENCRYPTION_KEY` is now **optional** in composable-agents (it is no longer used here); it must still be set on the mcp-raganything service that owns the registry.

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

The Todo List, Filesystem, and Sub-Agent middlewares are **always installed** by `create_deep_agent` defaults and cannot be toggled via the YAML configuration. Sub-agent delegation is enabled automatically when `subagents` is non-empty.

---

## Backends

The `BackendConfig` schema controls where agent state and checkpoints are persisted.

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | `BackendType` (`state` \| `store`) | `state` | Backend kind. `state` = in-memory LangGraph state, `store` = LangGraph store-backed. |
| `store_backend` | `Literal["memory", "postgres"]` | `memory"` | Where the LangGraph store lives. `memory` = in-process, `postgres` = PostgreSQL-backed (singleton reused across all agent builds). |
| `checkpoint_backend` | `Literal["memory", "postgres"]` | `memory"` | Where the LangGraph checkpointer lives. `memory` = in-process, `postgres` = PostgreSQL-backed (singleton reused across all agent builds). |

### Supported `type` values

| Name | Enum Value | Description |
|---|---|---|
| State | `state` | Default in-memory state backend (no extra config). |
| Store | `store` | LangGraph store-based backend. The store itself is backed by `store_backend`. |

### Postgres-backed store and checkpointer

When `store_backend` or `checkpoint_backend` is set to `"postgres"`, the framework instantiates a single `PostgresStore` / `PostgresSaver` (from `langgraph-checkpoint-postgres`) and **reuses the same instance across every agent build**. This avoids opening a new connection pool per agent.

> **Note:** The `langgraph-checkpoint-postgres` package is required and is included in the project dependencies.

Example YAML enabling Postgres for both store and checkpointer:

```yaml
name: persistent-agent
backend:
  type: store
  store_backend: postgres
  checkpoint_backend: postgres
```

The `StoreBackend` is wired with a per-run namespace via `StoreBackend(store=store, namespace=lambda r: ("filesystem",))` (the deprecated `StoreBackend(runtime)` pattern has been removed).

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
| `GET` | `/api/v1/threads/{thread_id}/history` | Get thread history grouped by turn (`ThreadHistory`) | `200` |
| `GET` | `/api/v1/threads/{thread_id}/trace` | Get the flat list of `TraceEvent`s for a thread | `200` |
| `GET` | `/api/v1/threads/{thread_id}/messages` | List messages in a thread (projection from `trace_events`: `HUMAN_MESSAGE` + `AI_MESSAGE` only, backward-compat) | `200` |
| `POST` | `/api/v1/chat/{thread_id}` | Send a message and get the full response | `200` |
| `POST` | `/api/v1/chat/{thread_id}/stream` | Send a message and stream the response (SSE) | `200` |
| `POST` | `/api/v1/threads/{thread_id}/hitl` | Submit a human-in-the-loop decision | `200` |
| `GET` | `/api/v1/agents` | List all agent configs from `agents/` directory | `200` |
| `GET` | `/api/v1/agents/{agent_name}` | Get a specific agent configuration | `200` |
| `GET` | `/api/v1/store/files` | List file paths in the store (optional `prefix` query param) | `200` |
| `GET` | `/api/v1/store/files/{path}` | Get a single file's content by path | `200` |
| `PUT` | `/api/v1/store/files/{path}` | Create or replace a file in the store | `200` |
| `DELETE` | `/api/v1/store/files/{path}` | Delete a file from the store | `204` |
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
    "backend": {"type": "state", "store_backend": "memory", "checkpoint_backend": "memory"},
    "hitl": {"rules": {"write_file": true, "execute": {"allowed_decisions": ["approve", "reject"]}}},
    "subagents": [...]
  },
  {
    "name": "example-agent",
    "model": "openai:anthropic/claude-haiku-4.5:nitro",
    "system_prompt": "You are a helpful assistant.",
    "tools": [],
    "backend": {"type": "state", "store_backend": "memory", "checkpoint_backend": "memory"},
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
  "backend": {"type": "state", "store_backend": "memory", "checkpoint_backend": "memory"},
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

Response (Server-Sent Events, one `TraceEvent` JSON object per line):

```
data: {"id":"...","thread_id":"...","turn_id":"...","type":"HUMAN_MESSAGE","source":null,"name":null,"content":"Write a haiku about programming.","metadata":{},"timestamp":"2025-04-24T10:30:00.000000Z","sequence":0}

data: {"id":"...","thread_id":"...","turn_id":"...","type":"THINKING","source":null,"name":null,"content":"Hmm, a haiku needs 5-7-5 syllables...","metadata":{},"timestamp":"...","sequence":1}

data: {"id":"...","thread_id":"...","turn_id":"...","type":"CONTENT","source":null,"name":null,"content":"Lines","metadata":{},"timestamp":"...","sequence":2}

data: {"id":"...","thread_id":"...","turn_id":"...","type":"CONTENT","source":null,"name":null,"content":" of","metadata":{},"timestamp":"...","sequence":3}

data: {"id":"...","thread_id":"...","turn_id":"...","type":"CONTENT","source":null,"name":null,"content":" code","metadata":{},"timestamp":"...","sequence":4}

data: {"id":"...","thread_id":"...","turn_id":"...","type":"AI_MESSAGE","source":null,"name":null,"content":"Lines of code align...","metadata":{},"timestamp":"...","sequence":5}

data: [DONE]
```

#### `TraceEvent` format

Each `data:` line (except the final `[DONE]`) is a JSON-serialized `TraceEvent` with the following fields:

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique event ID. |
| `thread_id` | `string` | Owning thread ID. |
| `turn_id` | `string` | Turn ID grouping all events from one user message to the next AI reply. |
| `type` | `enum` | One of `HUMAN_MESSAGE`, `AI_MESSAGE`, `THINKING`, `CONTENT`, `TOOL_CALL`, `TOOL_RESULT`. |
| `source` | `string \| null` | Sub-agent name when the event was emitted by a sub-agent, `null` for the parent agent. |
| `name` | `string \| null` | Tool name (only for `TOOL_CALL` / `TOOL_RESULT`). |
| `content` | `string` | Text payload (message text, thinking text, content chunk, tool arguments/result). |
| `metadata` | `object` | Additional structured data (e.g. tool call ID, `{"status": ...}` for `AI_MESSAGE`). The structured response for an `AI_MESSAGE` is **not** in `metadata` — it lives in `content` as part of the JSON-serialized `Message`. See [Structured Output](#structured-output-response_format). |
| `timestamp` | `string` | ISO 8601 timestamp. |
| `sequence` | `int` | Monotonic sequence number within the thread (ordering). |

#### Error payload

On error the stream emits a single JSON object (NOT a valid `TraceEvent`) followed by `[DONE]`:

```
data: {"type":"error","data":"Agent execution failed: ..."}

data: [DONE]
```

Clients should check for `type === "error"` before parsing as `TraceEvent`.

#### Rendering guidance

- Render `THINKING` events in a collapsible reasoning panel.
- Append `CONTENT` events directly to the chat bubble (or the relevant sub-agent panel when `source` is set).
- Render `TOOL_CALL` as a badge and `TOOL_RESULT` as a terminal-style block.
- Group events by `source` to display sub-agent panels separately.
- Wait for the `AI_MESSAGE` event to finalize the turn.

This design prevents Cloudflare timeout issues (~100s on idle connections) because chunks and SSE pings (every 15s) keep the connection active.

### 6b. Get Thread History

```bash
curl http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890/history
```

Response (`200`) — `ThreadHistory`:

```json
{
  "thread": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "agent_name": "example-agent",
    "created_at": "2025-01-15T10:30:00.000000",
    "updated_at": "2025-01-15T10:30:05.000000"
  },
  "turns": [
    {
      "turn_id": "turn-uuid-1",
      "human_message": { "id": "...", "type": "HUMAN_MESSAGE", "content": "Hello", ... },
      "ai_message": { "id": "...", "type": "AI_MESSAGE", "content": "Hi!", ... },
      "events": [
        { "id": "...", "type": "THINKING", "source": null, "content": "...", ... },
        { "id": "...", "type": "TOOL_CALL", "source": "researcher", "name": "search", ... },
        { "id": "...", "type": "TOOL_RESULT", "source": "researcher", "name": "search", ... }
      ]
    }
  ]
}
```

`events` contains the intermediate events (`THINKING`, `CONTENT`, `TOOL_CALL`, `TOOL_RESULT`) for the turn, in `sequence` order. `human_message` and `ai_message` are the terminal `HUMAN_MESSAGE` / `AI_MESSAGE` events.

### 6c. Get Flat Trace

```bash
curl http://localhost:8000/api/v1/threads/a1b2c3d4-e5f6-7890-abcd-ef1234567890/trace
```

Response (`200`):

```json
{
  "events": [
    { "id": "...", "type": "HUMAN_MESSAGE", "content": "Hello", ... },
    { "id": "...", "type": "THINKING", "content": "...", ... },
    { "id": "...", "type": "AI_MESSAGE", "content": "Hi!", ... }
  ]
}
```

Returns the full flat list of `TraceEvent`s for the thread, ordered by `sequence`.

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
  if (data.type === "error") { console.error("Error:", data.data); return; }
  switch (data.type) {
    case "THINKING":   console.log("[Thinking]", data.content); break;
    case "CONTENT":    process.stdout.write(data.content); break;
    case "AI_MESSAGE": console.log("Final message:", data.content); break;
    case "TOOL_CALL":  console.log("Tool call:", data.name, data.content); break;
    case "TOOL_RESULT":console.log("Tool result:", data.name, data.content); break;
  }
};
```

The WebSocket stream emits `TraceEvent` JSON objects (same shape as the `/stream` SSE endpoint), then `[END]`. On error, emits `{"type":"error","data":"..."}` before `[END]`.

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

## Store File API

composable-agents exposes a small REST surface for managing **files in the LangGraph store**. Files are stored as UTF-8 text blobs keyed by a path string (e.g. `/skills/my-skill/SKILL.md`). The store is shared across all agents and backed by the same `BaseStore` instance configured per agent (`store_backend: memory` or `postgres`).

### Endpoints

| Method | Path | Description | Success Status |
|---|---|---|---|
| `GET` | `/api/v1/store/files?prefix=<prefix>` | List file paths matching `prefix` (default `/` = all) | `200` |
| `GET` | `/api/v1/store/files/{path}` | Retrieve a single file's content | `200` |
| `PUT` | `/api/v1/store/files/{path}` | Create or replace a file (body: `{"content": "..."}`) | `200` |
| `DELETE` | `/api/v1/store/files/{path}` | Delete a file (idempotent) | `204` |

The `{path}` segment uses FastAPI's `:path` converter, so it can contain slashes (e.g. `skills/my-skill/SKILL.md`). Do not include a leading slash in the URL.

### Listing files

```bash
curl 'http://localhost:8000/api/v1/store/files?prefix=/skills/'
```

Response (`200`) — a JSON array of path strings:

```json
["skills/code-review/SKILL.md", "skills/debugging/SKILL.md"]
```

### Getting a file

```bash
curl http://localhost:8000/api/v1/store/files/skills/code-review/SKILL.md
```

Response (`200`):

```json
{"path": "skills/code-review/SKILL.md", "content": "# Code Review Skill\n\n..."}
```

If the file does not exist, the API returns `404` with `{"detail": "File not found: skills/code-review/SKILL.md"}`.

### Creating or replacing a file

```bash
curl -X PUT http://localhost:8000/api/v1/store/files/skills/code-review/SKILL.md \
  -H "Content-Type: application/json" \
  -d '{"content": "# Code Review Skill\n\nReview code for correctness and security."}'
```

Response (`200`):

```json
{"path": "skills/code-review/SKILL.md", "content": "# Code Review Skill\n\nReview code for correctness and security."}
```

### Deleting a file

```bash
curl -X DELETE http://localhost:8000/api/v1/store/files/skills/code-review/SKILL.md
```

Response: `204 No Content`. The operation is idempotent — deleting a non-existent path does not raise.

### Agent Namespace

When an agent is created (or updated) with `skills` or `memory` configured, the selected files are **copied into a dedicated namespace** in the store, scoped to that agent:

- **Skills:** `/agents/{agent_name}/skills/{skill_name}/SKILL.md`
- **Memories:** `/agents/{agent_name}/memories/{filename}`

This ensures each agent only loads the skills and memories explicitly selected in its configuration, not every file in the global `/skills/` and `/memories/` directories.

When an agent is updated and a skill or memory is **removed** from the selection, the corresponding copy in the agent namespace is **deleted** automatically.

To discover which agents reference a given skill, use the usage-tracking endpoint:

```bash
curl http://localhost:8000/api/v1/store/skills/my-skill/usage
```

Response (`200`) — the list of agent names that have `my-skill` in their namespace:

```json
["code-reviewer", "research-assistant"]
```

---

## Skills Management

Skills are `SKILL.md` files stored in the LangGraph store under the `/skills/` prefix. They describe reusable capabilities that an agent can load via its `skills` config field. Skills can now be created, edited, and deleted **via the Store File API** or the **frontend UI** (dedicated "Skills" page in the sidebar).

### Creating a skill via curl

```bash
curl -X PUT http://localhost:8000/api/v1/store/files/skills/my-skill/SKILL.md \
  -H "Content-Type: application/json" \
  -d '{"content": "# my-skill\n\n## Description\nA skill for ..."}'
```

### Referencing a skill in an agent

In the agent YAML, point the `skills` field at the skill path (without the leading slash):

```yaml
name: my-agent
skills:
  - "skills/my-skill/"
```

In the frontend agent form, the Skills field is a **multi-select dropdown** (`PillMultiSelect`) that lists all available skills discovered in the store (paths matching `/skills/`), replacing the previous free-text input.

---

## Memories Management

Memories are Markdown files (e.g. `AGENTS.md`) stored in the LangGraph store, typically under the `/memories/` prefix. They provide persistent context that an agent loads via its `memory` config field. Memories can now be created, edited, and deleted **via the Store File API** or the **frontend UI** (dedicated "Memories" page in the sidebar).

### Creating a memory via curl

```bash
curl -X PUT http://localhost:8000/api/v1/store/files/memories/AGENTS.md \
  -H "Content-Type: application/json" \
  -d '{"content": "# Project Guidelines\n\n- Always write tests.\n- Follow the hexagonal architecture."}'
```

### Referencing a memory in an agent

In the agent YAML, point the `memory` field at the memory path:

```yaml
name: my-agent
memory:
  - "memories/AGENTS.md"
```

In the frontend agent form, the Memory field is a **multi-select dropdown** (`PillMultiSelect`) that lists all available memories from the store, replacing the previous free-text input.

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
    config.py                          # Pydantic Settings (env vars, DATABASE_URL normalization)
    dependencies.py                    # Dependency injection wiring
    alembic.ini                        # Alembic configuration
    alembic/
      env.py                           # Alembic env (async engine, model imports)
      versions/
        001_create_agent_configs_table.py
        002_create_threads_and_messages_tables.py
        005_create_trace_events_table.py   # Create trace_events table
        006_migrate_messages_to_trace_events.py  # Backfill trace_events from messages
        007_drop_messages_table.py          # Drop legacy messages table
    application/
      requests/
        chat.py                        # Request models (ChatRequest, CreateThreadRequest, HITLDecisionRequest)
      responses/
        thread_history.py               # ThreadHistory response DTO (thread + turns)
      routes/
        health.py                      # GET /health
        threads.py                     # CRUD /api/v1/threads
        chat.py                        # POST /api/v1/chat/{id} and /stream
        trace.py                       # GET /api/v1/threads/{id}/history and /trace
        agents.py                      # GET /api/v1/agents
        store.py                       # Store File API — /api/v1/store/files
        websocket.py                   # WS /api/v1/ws/{id}
      use_cases/
        send_message.py                # Invoke agent synchronously
        stream_message.py              # Stream agent response
        get_thread_history.py          # Build ThreadHistory from trace_events (group by turn_id)
        manage_store_file.py           # ListStoreFiles / GetStoreFile / PutStoreFile / DeleteStoreFile use cases
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
        agent_config_metadata.py       # AgentConfigMetadata (incl. description)
        mcp_server_config.py           # McpServerConfig, McpTransportType
        message.py                     # Message (role, content, timestamp, tool_calls) — projection model
        thread.py                       # Thread (id, agent_name, timestamps) — no more MessageModel
        trace_event.py                  # TraceEvent entity + TraceEventType enum (6 types)
        tracing_config.py              # TracingConfig, TracingProviderType
      ports/
        agent_config_loader.py         # Abstract: load config from file
        agent_config_repository.py     # Abstract: CRUD for agent config metadata
        agent_config_store.py          # Abstract: object storage for YAML blobs
        agent_registry.py              # Abstract: get_runner(name), list_agents(), close()
        agent_runner.py                # Abstract: invoke, stream, HITL operations
        mcp_tool_loader.py             # Abstract: load MCP tools
        store_file_repository.py        # Abstract: file CRUD on the LangGraph store (StoreFileRepository port)
        thread_repository.py           # Abstract: CRUD for threads
        trace_event_repository.py      # Abstract: persist/append/list TraceEvents
        tracing_provider.py            # Abstract: tracing lifecycle
      exceptions.py                    # DomainError hierarchy (incl. AgentNotFoundError, StorageError)
    infrastructure/
      env_utils.py                     # ${VAR_NAME} environment variable resolution
      database/
        models/
          base.py                      # SQLAlchemy DeclarativeBase
          agent_config.py              # AgentConfigModel (ORM)
          thread.py                    # ThreadModel (ORM) — MessageModel removed
          trace_event.py               # TraceEventModel (ORM)
      deepagent/
        adapter.py                     # DeepAgentRunner (LangGraph adapter) — emits TraceEvent
        factory.py                     # create_agent_from_config (resolves tools, backend)
        registry.py                    # DeepAgentRegistry (lazy loading + caching from agents/ dir)
        example_tools.py               # Example tools: current_time, word_count
      mcp/
        adapter.py                     # LangchainMcpToolLoader
      minio_store/
        adapter.py                     # MinioAgentConfigStore (YAML blob storage)
      persistent_registry/
        adapter.py                     # PersistentAgentRegistry (MinIO + Postgres backed)
      store_file/
        adapter.py                     # LangGraphStoreFileRepository (LangGraph BaseStore adapter)
      postgres_repository/
        adapter.py                     # PostgresAgentConfigRepository
      postgres_thread/
        adapter.py                     # PostgresThreadRepository (thread persistence)
        models.py                     # Re-exports ThreadModel
      postgres_trace/
        adapter.py                     # PostgresTraceEventRepository (trace_events persistence)
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

`agents/research-assistant.yaml` -- an agent with custom tools.

```yaml
name: research-assistant
model: "claude-sonnet-4-5-20250929"
system_prompt: |
  You are a research assistant specialized in technical documentation.
  Always cite your sources and provide structured summaries.
tools:
  - "src.infrastructure.deepagent.example_tools:current_time"
  - "src.infrastructure.deepagent.example_tools:word_count"
backend:
  type: state
debug: false
```

### Code Reviewer with HITL and Subagents

`agents/code-reviewer.yaml` -- a multi-agent system with human-in-the-loop approval. The Sub-Agent middleware is installed automatically because `subagents` is non-empty.

```yaml
name: code-reviewer
model: "claude-sonnet-4-5-20250929"
system_prompt: |
  You are an expert code reviewer. Analyze code for correctness,
  performance, security, and maintainability.
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

The database uses a flat normalized schema. Thread persistence relies on a single `trace_events` table as the source of truth for all conversation activity (the legacy `messages` table has been dropped — see [Breaking changes](#breaking-changes)).

| Table | Description |
|---|---|
| `threads` | One row per conversation thread. Columns: `id` (PK, VARCHAR 36), `agent_name`, `created_at`, `updated_at`. |
| `trace_events` | One row per trace event. Columns: `id` (PK), `thread_id` (FK to `threads.id`, CASCADE delete), `turn_id`, `type` (enum: `HUMAN_MESSAGE`, `AI_MESSAGE`, `THINKING`, `CONTENT`, `TOOL_CALL`, `TOOL_RESULT`), `source` (sub-agent name or null), `name` (tool name or null), `content` (text), `metadata` (JSONB), `timestamp`, `sequence` (int, monotonic per thread). |
| `agent_configs` | Agent configuration metadata. |

Indexes on `trace_events`:

- `ix_trace_events_thread_id` — fast lookup of all events for a thread.
- `ix_trace_events_thread_id_sequence` — ordered retrieval of events within a thread (used by `/trace` and `/history`).
- `ix_trace_events_thread_id_turn_id` — grouping events by turn (used by `/history`).

The `messages` table has been **dropped** (migration `007`). Its data was backfilled into `trace_events` by migration `006` (each old `Message` row became a `HUMAN_MESSAGE` or `AI_MESSAGE` event). The legacy `GET /api/v1/threads/{id}/messages` endpoint is preserved as a backward-compatible projection that filters `trace_events` to `HUMAN_MESSAGE` + `AI_MESSAGE` rows.

### Migrations (Alembic)

Alembic migrations live in `src/alembic/versions/` and run **automatically at startup** (via `asyncio.to_thread()` in the FastAPI lifespan). You never need to run `alembic upgrade` manually in normal operation.

Relevant migrations for the trace events refactor:

| Migration | Description |
|---|---|
| `005_create_trace_events_table` | Creates the `trace_events` table with the 3 indexes above. |
| `006_migrate_messages_to_trace_events` | Backfills `trace_events` from existing `messages` rows (`role = "human"` → `HUMAN_MESSAGE`, `role = "ai"` → `AI_MESSAGE`). |
| `007_drop_messages_table` | Drops the legacy `messages` table. |
| `010_add_description_to_agent_configs` | Adds a `description VARCHAR(500)` column to the `agent_configs` table. |

Migrations owning the shared `mcp_servers` table (consumed by mcp-raganything):

| Migration | Description |
|---|---|
| `008_create_mcp_servers_table` | Creates the `mcp_servers` table (name, transport, url, Fernet-encrypted `headers`/`env`/`auth_token`, tool_count, timestamps). |
| `009_alter_mcp_servers_add_openapi` | Adds `source_type` (`"external"` \| `"openapi"`) and `openapi_url` columns so an MCP server can be generated from an OpenAPI spec. |

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

- **Hexagonal architecture**: `ThreadRepository` (port) -> `PostgresThreadRepository` (adapter), `TraceEventRepository` (port) -> `PostgresTraceEventRepository` (adapter). The domain layer has no knowledge of SQLAlchemy.
- **Session-per-method**: Each repository method creates its own `AsyncSession` from the engine, ensuring thread-safety for concurrent FastAPI requests.
- **Connection pooling**: `AsyncAdaptedQueuePool` with `pool_size=20`, `max_overflow=20`, and `pool_pre_ping=True`.
- **Cascade deletes**: Deleting a thread automatically deletes all its `trace_events` via `ON DELETE CASCADE` at both the SQL and ORM level.
- **Event ordering**: `trace_events` are sorted by `sequence` (monotonic per thread). The adapter applies a defensive Python sort as well.
- **JSONB columns**: `metadata` is stored as PostgreSQL `JSONB`, allowing structured data (tool call IDs, structured responses) without additional join tables.
- **Single source of truth**: `trace_events` is the only persistence for conversation activity. `messages` is no longer a table; the `/messages` endpoint is a read-only projection.

---

## Breaking Changes

This release replaces the legacy `StreamEvent` / `messages`-based model with a unified `TraceEvent` model.

### `StreamEvent` removed

The old SSE payload format (`{"type": "thinking" | "content" | "message" | "structured" | "error", "data": "..."}`) is **removed**. The `/stream` and WebSocket endpoints now emit `TraceEvent.model_dump_json()` objects (see [TraceEvent format](#traceevent-format)). Clients must be updated to parse the new schema. The only non-`TraceEvent` payload is the error object `{"type": "error", "data": "..."}` emitted on failure (followed by `[DONE]`).

### `messages` table dropped

The `messages` PostgreSQL table has been dropped (migration `007`). All conversation activity is now stored in `trace_events`. Migration `006` backfills `trace_events` from existing `messages` rows, so no data is lost when upgrading. The `GET /api/v1/threads/{id}/messages` endpoint is preserved as a backward-compatible projection (filters `trace_events` to `HUMAN_MESSAGE` + `AI_MESSAGE`).

### `AgentRunner` API

The `AgentRunner` port signatures have changed:

- `invoke(thread_id, message, turn_id) -> tuple[Message, list[TraceEvent]]`
- `stream(thread_id, message, turn_id) -> AsyncIterator[TraceEvent]`

Adapters and tests calling the old `invoke(thread_id, message) -> Message` / `stream(...) -> AsyncIterator[StreamEvent]` signatures must be updated.

### Migrations

Migrations `005`, `006`, `007` run automatically on startup. They are idempotent and safe to run on an existing database with data.

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
| `DATABASE_URL` | **required** | PostgreSQL connection URL (e.g. `postgresql://user:pass@host:5432/db`). Automatically normalized to `postgresql+asyncpg://` for async SQLAlchemy. `sslmode` and `channel_binding` query params are extracted and passed via `connect_args` (asyncpg doesn't accept them in the URL). |
| `POSTGRES_STATEMENT_CACHE_SIZE` | `100` (asyncpg default) | Set to `0` when using a connection pooler (Neon, PgBouncer, etc.). |

> **⚠️ Breaking change:** `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DATABASE` are no longer used. Migrate to `DATABASE_URL`.

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
   | `DATABASE_URL` | `postgresql://postgres:pass@roundhouse.proxy.rlwy.net:33019/railway` | Railway PostgreSQL connection URL |
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
- How to add custom tools and backends
- How the YAML schema works
- Running tests and linting
- Code style conventions

---

## License

This project does not currently include a license file. Contact the maintainers for licensing information.
