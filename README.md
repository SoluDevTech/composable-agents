# composable-agents

Configure Deep Agent LangGraph agents in YAML and expose them via FastAPI.

**composable-agents** is a Python framework that lets you declare AI agents as simple YAML files and instantly expose them as a full-featured HTTP API. It is built on [deepagents](https://pypi.org/project/deepagents/) (LangGraph-based Deep Agent) with a strict hexagonal architecture, making every component testable and replaceable.

The server supports **multi-agent mode**: multiple agents are defined as separate YAML files in an `agents/` directory, each thread is bound to a specific agent at creation time, and agents are lazily instantiated on first use.

---

## Quickstart (5 minutes)

### Prerequisites

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) package manager
- An API key for at least one LLM provider (Anthropic, OpenAI, or Google)

### Installation

```bash
git clone https://github.com/your-org/composable-agents.git
cd composable-agents
uv sync
cp .env.example .env
```

Edit `.env` and add your API key:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...
# or
GOOGLE_API_KEY=...
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
uv run python -m src serve
```

The API starts on `http://localhost:8000`. On startup, the server reads the `AGENTS_DIR` environment variable (default: `./agents`) to discover available agents. Agents are not loaded into memory until a thread references them for the first time.

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
| `model_kwargs` | `dict` | `null` | Extra keyword arguments passed to `init_chat_model()` (e.g. `base_url`, `api_key`). |
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

For OpenAI-compatible endpoints (OpenRouter, LiteLLM, vLLM, etc.), set the `OPENAI_BASE_URL` environment variable to point to your endpoint. The OpenAI SDK reads this variable automatically. Alternatively, use `model_kwargs` in the YAML to set `base_url` and `api_key` per-agent.

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
data: Lines
data:  of
data:  code
data:  align
data: ...
```

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
    | - DeepAgentRegistry|
    | - YamlConfigLoader |
    | - InMemoryThreads  |
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
    main.py                            # FastAPI app creation and lifespan
    config.py                          # Pydantic Settings (env vars)
    dependencies.py                    # Dependency injection wiring
    application/
      requests/
        chat.py                        # Request models (ChatRequest, CreateThreadRequest, HITLDecisionRequest)
      routes/
        health.py                      # GET /health
        threads.py                     # CRUD /api/v1/threads
        chat.py                        # POST /api/v1/chat/{id} and /stream
        hitl.py                        # POST /api/v1/threads/{id}/hitl
        agents.py                      # GET /api/v1/agents
        websocket.py                   # WS /api/v1/ws/{id}
      use_cases/
        send_message.py                # Invoke agent synchronously
        stream_message.py              # Stream agent response
        hitl_decision.py               # Approve / reject / edit HITL decisions
        load_agent_config.py           # Load and validate a YAML config
        thread_management.py           # Create / get / list / delete threads
    domain/
      entities/
        agent_config.py                # AgentConfig, BackendConfig, HITLConfig, SubAgentConfig
        mcp_server_config.py           # McpServerConfig, McpTransportType
        message.py                     # Message (role, content, timestamp, tool_calls)
        thread.py                      # Thread (id, agent_name, messages, timestamps)
        tracing_config.py              # TracingConfig, TracingProviderType
      ports/
        agent_config_loader.py         # Abstract: load config from file
        agent_registry.py              # Abstract: get_runner(name), list_agents(), close()
        agent_runner.py                # Abstract: invoke, stream, HITL operations
        mcp_tool_loader.py             # Abstract: load MCP tools
        thread_repository.py           # Abstract: CRUD for threads
        tracing_provider.py            # Abstract: tracing lifecycle
      exceptions.py                    # DomainError hierarchy (incl. AgentNotFoundError)
    infrastructure/
      env_utils.py                     # ${VAR_NAME} environment variable resolution
      deepagent/
        adapter.py                     # DeepAgentRunner (LangGraph adapter)
        factory.py                     # create_agent_from_config (resolves tools, middleware, backend)
        registry.py                    # DeepAgentRegistry (lazy loading + caching from agents/ dir)
        example_tools.py               # Example tools: current_time, word_count
      mcp/
        adapter.py                     # LangchainMcpToolLoader
      memory_thread/
        adapter.py                     # InMemoryThreadRepository
      yaml_config/
        adapter.py                     # YamlAgentConfigLoader
      tracing/
        langfuse_adapter.py            # Langfuse tracing provider
        phoenix_adapter.py             # Phoenix tracing provider
        noop_adapter.py                # No-op tracing provider (default)
  tests/
    conftest.py
    doubles/
      fake_agent_runner.py             # FakeAgentRunner for unit tests
      fake_agent_config_loader.py      # FakeAgentConfigLoader for unit tests
      fake_agent_registry.py           # FakeAgentRegistry for unit tests
      fake_mcp_tool_loader.py          # FakeMcpToolLoader for unit tests
      fake_tracing_provider.py         # FakeTracingProvider for unit tests
    unit/
      test_agent_config.py
      test_deep_agent_runner.py
      test_env_utils.py
      test_factory.py
      test_factory_mcp_integration.py
      test_hitl.py
      test_langfuse_adapter.py
      test_load_agent_config_use_case.py
      test_mcp_adapter.py
      test_mcp_lifecycle.py
      test_mcp_server_config.py
      test_noop_tracing.py
      test_phoenix_adapter.py
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

## Environment Variables

Configured via `.env` file or environment variables. See `.env.example`.

| Variable | Default | Description |
|---|---|---|
| `AGENTS_DIR` | `./agents` | Directory containing agent YAML configuration files. |
| `ANTHROPIC_API_KEY` | -- | API key for Anthropic models. |
| `OPENAI_API_KEY` | -- | API key for OpenAI models. |
| `GOOGLE_API_KEY` | -- | API key for Google models. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible endpoints. Set to use OpenRouter, LiteLLM, vLLM, etc. |
| `HOST` | `0.0.0.0` | Server bind host. |
| `PORT` | `8000` | Server bind port. |

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
