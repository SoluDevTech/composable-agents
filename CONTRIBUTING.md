# Contributing to composable-agents

Thank you for your interest in contributing. This document explains the project structure, conventions, and how to extend the system.

---

## Project Architecture

composable-agents follows a strict **hexagonal architecture** (also known as ports and adapters). The key principle is that the domain layer has zero dependencies on infrastructure or frameworks.

```
src/
  domain/           # Pure business logic. No imports from infrastructure or frameworks.
    entities/       # Data models (AgentConfig, Thread, Message)
    ports/          # Abstract interfaces (AgentRunner, ThreadRepository, AgentConfigLoader)
    exceptions.py   # Domain-specific exception hierarchy
  application/      # Use cases that orchestrate domain logic. Depends only on domain.
    use_cases/      # SendMessage, StreamMessage, HITL decisions, thread management, store file management
    requests/       # Pydantic request models for the API layer
    routes/         # FastAPI route handlers (health, threads, chat, trace, agents, store, websocket)
  infrastructure/   # Concrete implementations of domain ports
    deepagent/      # LangGraph Deep Agent adapter + factory
    yaml_config/    # YAML config file loader
    memory_thread/  # In-memory thread storage
  config.py         # Pydantic Settings (environment variables)
  dependencies.py   # Dependency injection wiring
  main.py           # FastAPI app creation
```

### Dependency Rule

- `domain/` imports **nothing** from `application/` or `infrastructure/`.
- `application/` imports from `domain/` only (ports and entities).
- `infrastructure/` imports from `domain/` to implement ports.
- `routes/` and `dependencies.py` import from both `application/` and `infrastructure/` to wire everything together.

---

## How to Add a Custom Tool

Tools are standard LangChain tools using the `@tool` decorator. To add a new tool:

### 1. Create a Python file with your tool

```python
# src/infrastructure/deepagent/my_tools.py
from langchain_core.tools import tool


@tool
def search_web(query: str) -> str:
    """Search the web for information on a given query."""
    # Your implementation here
    return f"Results for: {query}"


@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression)  # Use a safe evaluator in production
        return str(result)
    except Exception as e:
        return f"Error: {e}"
```

### 2. Reference the tool in your YAML config

Use the `module.path:attribute_name` format:

```yaml
name: my-agent
tools:
  - "src.infrastructure.deepagent.my_tools:search_web"
  - "src.infrastructure.deepagent.my_tools:calculate"
```

### 3. Validate

```bash
uv run python -m src dry-run agents/my-agent.yaml
```

The `dry-run` command will attempt to import and resolve the tool references, catching errors before the server starts.

---

## How the YAML Schema Works

The YAML configuration is validated by the `AgentConfig` Pydantic model defined in `src/domain/entities/agent_config.py`.

Key points:

- `AgentConfig` is a **frozen** Pydantic `BaseModel` (immutable after creation).
- Validation includes:
  - `name` must be 1-100 characters.
  - `description` is an optional `str | None` (max 500 characters), persisted in the `agent_configs` table (migration `010_add_description_to_agent_configs`) and exposed via `AgentConfigMetadata`.
  - `system_prompt` and `system_prompt_file` are mutually exclusive (enforced by `@model_validator`).
  - `backend.type` must match the `BackendType` enum (`state` or `store`).
  - `backend.store_backend` and `backend.checkpoint_backend` must be `"memory"` or `"postgres"`.
  - `hitl.rules` values are either `bool` or `InterruptRule` objects.
  - `subagents` entries require `name` and `description`.
  - `subagents[*].agent_ref` is an optional `str | None` referencing another existing agent by name. At runner-build time the backend resolves the referenced agent's `model`, `system_prompt`, `mcp_servers`, `tools`, and `response_format`; explicit values on the `SubAgentConfig` override the inherited ones. **One level only** — the referenced agent's own `subagents` are not resolved. Validation rejects self-references (`agent_ref == agent name`) and non-existent references with a `ConfigError` at create/update time. When an agent is updated or deleted, any agents referencing it via `agent_ref` are also invalidated in the registry.

To modify the schema, edit `src/domain/entities/agent_config.py` and regenerate the JSON schema:

```bash
uv run python -m src schema > agent-config-schema.json
```

---

## How to Add a New Backend

### 1. Add a value to the `BackendType` enum

In `src/domain/entities/agent_config.py`:

```python
class BackendType(StrEnum):
    STATE = "state"
    STORE = "store"
    MY_BACKEND = "my_backend"  # Add your new type
```

### 2. Handle it in `_resolve_backend`

In `src/infrastructure/deepagent/factory.py`:

```python
def _resolve_backend(config: AgentConfig):
    match config.backend.type:
        case BackendType.STATE:
            return None
        case BackendType.STORE:
            return lambda rt: StoreBackend(store=store, namespace=lambda r: ("filesystem",))
        case BackendType.MY_BACKEND:
            return MyBackend(config.backend)  # Your implementation
```

### 3. Use it in YAML

```yaml
name: my-agent
backend:
  type: my_backend
  store_backend: memory
  checkpoint_backend: memory
```

---

## Store File API

Files in the LangGraph store (skills, memories, any text blob) are managed through a dedicated set of use cases, a domain port, and an infrastructure adapter, following the same hexagonal pattern as the rest of the codebase.

### Routes (`src/application/routes/store.py`)

| Method | Path | Handler |
|---|---|---|
| `GET` | `/api/v1/store/files` | `list_store_files` (optional `prefix` query param) |
| `GET` | `/api/v1/store/files/{path:path}` | `get_store_file` |
| `PUT` | `/api/v1/store/files/{path:path}` | `put_store_file` (body: `StoreFilePutRequest`) |
| `DELETE` | `/api/v1/store/files/{path:path}` | `delete_store_file` |

Response DTOs: `StoreFileResponse` (`path`, `content`) and `StoreFilePutRequest` (`content`). The `{path:path}` converter allows slashes in the path segment. A missing file on `GET` raises `StoreFileNotFoundError` (`src/domain/errors/store_file.py`), resulting in a `404`.

### Use Cases (`src/application/use_cases/manage_store_file.py`)

Each use case is a thin pass-through to the repository (SRP — one class per action):

| Use Case | Method | Description |
|---|---|---|
| `ListStoreFilesUseCase` | `execute(prefix="/") -> list[str]` | List file paths matching the prefix. |
| `GetStoreFileUseCase` | `execute(path) -> str \| None` | Retrieve a single file's content; `None` if not found. |
| `PutStoreFileUseCase` | `execute(path, content) -> str` | Create or replace a file; returns the stored content. |
| `DeleteStoreFileUseCase` | `execute(path) -> None` | Delete a file (idempotent). |

All use cases are `async` and accept a `StoreFileRepository` via constructor injection.

### Port — `StoreFileRepository` (`src/domain/ports/store_file_repository.py`)

Abstract interface for file CRUD on a namespace-scoped key-value store:

| Method | Signature |
|---|---|
| `list_files` | `(prefix: str) -> list[str]` |
| `get_file` | `(path: str) -> str \| None` |
| `put_file` | `(path: str, content: str) -> None` |
| `delete_file` | `(path: str) -> None` |

`delete_file` is idempotent — implementations must not raise if the path does not exist.

### Adapter — `LangGraphStoreFileRepository` (`src/infrastructure/store_file/adapter.py`)

Implements `StoreFileRepository` on top of a LangGraph `BaseStore` (`InMemoryStore` or `AsyncPostgresStore`):

- Files are stored as `{"content": str, "encoding": "utf-8"}` values keyed by path under the `("filesystem",)` namespace by default (configurable via the `namespace` constructor arg).
- `list_files` uses `asearch(namespace, limit=100)` and filters client-side by `str.startswith(prefix)`.
- `get_file` returns `item.value.get("content")` (or `None` if the item is missing or malformed).
- `put_file` uses `aput` with the content dict.
- `delete_file` uses `adelete` (idempotent).

### Dependency injection

The four use cases are wired in `src/dependencies.py` via `get_list_store_files_use_case`, `get_get_store_file_use_case`, `get_put_store_file_use_case`, and `get_delete_store_file_use_case`. They share a single `LangGraphStoreFileRepository` instance built from the same store used by agent backends.

---

## Running Tests

The project uses **pytest** with **pytest-asyncio** for async test support. All tests are pure unit tests with no external dependencies (LLM calls are fully faked).

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=src

# Run a specific test file
uv run pytest tests/unit/test_routes.py -v

# Run a specific test class
uv run pytest tests/unit/test_routes.py::TestChatRoutes -v
```

### Test Doubles

Test doubles are located in `tests/doubles/`:

- `FakeAgentRunner` -- implements `AgentRunner` with deterministic responses.
- `FakeAgentConfigLoader` -- implements `AgentConfigLoader` with in-memory configs.

These are wired into the test suite via `tests/unit/test_routes.py` fixtures using `override_dependencies()`.

---

## Running Linting and Type Checking

```bash
# Lint with ruff
uv run ruff check .

# Auto-fix lint issues
uv run ruff check . --fix

# Type check with mypy
uv run mypy src/
```

---

## Code Style

- **Formatter/Linter**: ruff (configured via pyproject.toml or defaults).
- **Type hints**: Required on all public functions and methods.
- **Docstrings**: Required on all public classes and methods. French is acceptable for internal domain comments; English is preferred for docstrings.
- **Naming**: snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants.
- **Pydantic**: All data models use Pydantic v2 `BaseModel`.
- **Async**: All use cases and route handlers are `async`.

---

## Submitting Changes

1. Create a feature branch from `main`.
2. Write tests for your changes (the test suite must stay green).
3. Run the full validation:
   ```bash
   for f in agents/*.yaml; do uv run python -m src validate "$f"; done
   uv run pytest tests/ -v
   uv run ruff check .
   uv run mypy src/
   ```
4. Open a pull request with a clear description of what was changed and why.
