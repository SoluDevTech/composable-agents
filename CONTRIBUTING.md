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
    use_cases/      # SendMessage, StreamMessage, HITL decisions, thread management
    requests/       # Pydantic request models for the API layer
    routes/         # FastAPI route handlers (thin layer: validate input, call use case, return response)
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
  - `system_prompt` and `system_prompt_file` are mutually exclusive (enforced by `@model_validator`).
  - `middleware` values must match the `MiddlewareType` enum.
  - `backend.type` must match the `BackendType` enum.
  - `hitl.rules` values are either `bool` or `InterruptRule` objects.
  - `subagents` entries require `name` and `description`.

To modify the schema, edit `src/domain/entities/agent_config.py` and regenerate the JSON schema:

```bash
uv run python -m src schema > agent-config-schema.json
```

---

## How to Add a New Middleware

### 1. Add a value to the `MiddlewareType` enum

In `src/domain/entities/agent_config.py`:

```python
class MiddlewareType(StrEnum):
    TODO_LIST = "todo_list"
    FILESYSTEM = "filesystem"
    SUB_AGENT = "sub_agent"
    MY_MIDDLEWARE = "my_middleware"  # Add your new type
```

### 2. Register it in the factory

In `src/infrastructure/deepagent/factory.py`, add the mapping:

```python
from my_package import MyMiddleware

MIDDLEWARE_MAP: dict[MiddlewareType, type] = {
    MiddlewareType.TODO_LIST: FilesystemMiddleware,
    MiddlewareType.FILESYSTEM: FilesystemMiddleware,
    MiddlewareType.SUB_AGENT: SubAgentMiddleware,
    MiddlewareType.MY_MIDDLEWARE: MyMiddleware,  # Register here
}
```

### 3. Use it in YAML

```yaml
name: my-agent
middleware:
  - my_middleware
```

---

## How to Add a New Backend

### 1. Add a value to the `BackendType` enum

In `src/domain/entities/agent_config.py`:

```python
class BackendType(StrEnum):
    STATE = "state"
    STORE = "store"
    FILESYSTEM = "filesystem"
    COMPOSITE = "composite"
    MY_BACKEND = "my_backend"  # Add your new type
```

### 2. Handle it in `_resolve_backend`

In `src/infrastructure/deepagent/factory.py`:

```python
def _resolve_backend(config: AgentConfig):
    match config.backend.type:
        case BackendType.STATE:
            return None
        case BackendType.FILESYSTEM:
            return FilesystemBackend(root_dir=config.backend.root_dir or "./workspace")
        case BackendType.STORE:
            return lambda rt: StoreBackend(rt)
        case BackendType.MY_BACKEND:
            return MyBackend(config.backend.root_dir)  # Your implementation
        case BackendType.COMPOSITE:
            return None
```

### 3. Use it in YAML

```yaml
name: my-agent
backend:
  type: my_backend
  root_dir: "./data"
```

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
