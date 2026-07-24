import importlib
import logging
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import StoreBackend
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import AsyncPostgresStore
from pydantic import BaseModel

from src.config import Settings
from src.domain.entities.agent_config import AgentConfig, SubAgentConfig
from src.domain.logging.messages import LogMessage
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.prompt_manager import PromptManager
from src.infrastructure.deepagent.schema_utils import schema_to_pydantic_model

logger = logging.getLogger(__name__)


def _to_pg_conn_string(database_url: str) -> str:
    """Convert an asyncpg-normalized URL to a plain PostgreSQL connection string.

    The ``Settings.database_url`` is normalized to ``postgresql+asyncpg://`` for
    use with SQLAlchemy/asyncpg. langgraph-postgres uses ``psycopg`` and expects
    a plain ``postgresql://`` URL. This strips the ``+asyncpg`` driver suffix.

    Args:
        database_url: The normalized database URL (``postgresql+asyncpg://...``).

    Returns:
        A plain ``postgresql://`` connection string.
    """
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


_pg_store: AsyncPostgresStore | None = None
_pg_checkpointer: AsyncPostgresSaver | None = None
_pg_store_cm: Any = None
_pg_checkpointer_cm: Any = None
_memory_store: InMemoryStore | None = None


def _get_memory_store() -> InMemoryStore:
    """Get or create a singleton ``InMemoryStore`` shared across all agents.

    This ensures that files written via the Store File API (which also uses this
    singleton when ``store_backend`` is ``"memory"``) are visible to agents that
    use the in-memory store.
    """
    global _memory_store
    if _memory_store is None:
        _memory_store = InMemoryStore()
    return _memory_store


async def _get_shared_store():
    """Get the global shared store instance.

    If the Postgres store was initialized at startup (by ``dependencies.py``),
    use that. Otherwise fall back to the shared ``InMemoryStore`` singleton.
    This ensures the Store File API and all agents share the same store,
    regardless of per-agent ``store_backend`` config.
    """
    if _pg_store is not None:
        return _pg_store
    try:
        return await _create_postgres_store()
    except Exception:
        return _get_memory_store()


async def _create_postgres_store(settings: Settings | None = None) -> AsyncPostgresStore:
    """Get or create a singleton ``AsyncPostgresStore`` backed by Postgres.

    The store is created once and reused across all agent creations to avoid
    leaking connection pools. Schema migrations are applied on first creation.
    The async context manager reference is kept alive to prevent premature
    connection closure by the garbage collector.

    Args:
        settings: Optional settings override. Defaults to a fresh ``Settings``.

    Returns:
        A configured ``AsyncPostgresStore`` with schema migrations applied.
    """
    global _pg_store, _pg_store_cm
    if _pg_store is not None:
        return _pg_store
    s = settings or Settings()
    conn_string = _to_pg_conn_string(s.database_url)
    _pg_store_cm = AsyncPostgresStore.from_conn_string(conn_string)
    _pg_store = await _pg_store_cm.__aenter__()
    await _pg_store.setup()
    return _pg_store


async def _create_postgres_checkpointer(settings: Settings | None = None) -> AsyncPostgresSaver:
    """Get or create a singleton ``AsyncPostgresSaver`` checkpointer backed by Postgres.

    The checkpointer is created once and reused across all agent creations to
    avoid leaking connection pools. Schema migrations are applied on first
    creation. The async context manager reference is kept alive to prevent
    premature connection closure by the garbage collector.

    Args:
        settings: Optional settings override. Defaults to a fresh ``Settings``.

    Returns:
        A configured ``AsyncPostgresSaver`` with schema migrations applied.
    """
    global _pg_checkpointer, _pg_checkpointer_cm
    if _pg_checkpointer is not None:
        return _pg_checkpointer
    s = settings or Settings()
    conn_string = _to_pg_conn_string(s.database_url)
    _pg_checkpointer_cm = AsyncPostgresSaver.from_conn_string(conn_string)
    _pg_checkpointer = await _pg_checkpointer_cm.__aenter__()
    await _pg_checkpointer.setup()
    return _pg_checkpointer


def _resolve_response_format(value: dict[str, Any] | None) -> tuple[type[BaseModel] | None, dict[str, Any] | None]:
    """Resolve a ``response_format`` config value into ``(model, schema_dict)``.

    Args:
        value: The agent/subagent ``response_format`` config (a JSON Schema dict
            or ``None``).

    Returns:
        Tuple of ``(pydantic_model_or_none, schema_dict_or_none)``. The model is
        used for post-extraction validation/stripping; the dict is passed to
        deepagents' native ``response_format`` parameter.
    """
    if value is None:
        return None, None
    return schema_to_pydantic_model(value), value


def _resolve_tools(config: AgentConfig) -> list | None:
    """Charge les tools depuis leurs chemins Python (module:attribute)."""
    if not config.tools:
        return None
    tools = []
    for tool_path in config.tools:
        module_path, _, attr_name = tool_path.rpartition(":")
        if not module_path or not attr_name:
            logger.error(LogMessage.TOOL_FORMAT_INVALID, tool_path)
            raise ValueError(
                f"Invalid tool format '{tool_path}'. "
                f"Expected: 'module.path:tool_name' (e.g., 'mypackage.tools:my_tool')"
            )
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            logger.exception(LogMessage.TOOL_MODULE_NOT_FOUND, tool_path)
            raise ValueError(f"Module not found for tool '{tool_path}': {e}") from e

        if not hasattr(module, attr_name):
            available = [a for a in dir(module) if not a.startswith("_")]
            logger.error(LogMessage.TOOL_ATTRIBUTE_NOT_FOUND, attr_name, module_path)
            raise ValueError(f"Attribute '{attr_name}' not found in '{module_path}'. Available: {available}")
        tools.append(getattr(module, attr_name))
    return tools


def _resolve_backend(store):
    """Create the backend for the agent.

    The only supported backend is ``StoreBackend`` which reads/writes files
    from the shared LangGraph store (Postgres). This ensures skills and
    memories created via the Store File API are visible to all agents.

    Args:
        store: The shared store instance (Postgres or InMemoryStore).

    Returns:
        A ``StoreBackend`` instance.
    """
    return StoreBackend(store=store, namespace=lambda _r: ("filesystem",))


def _resolve_interrupt_on(config: AgentConfig) -> dict | None:
    """Convertit la config HITL en dict pour create_deep_agent."""
    if not config.hitl.rules:
        return None
    result = {}
    for tool_name, rule in config.hitl.rules.items():
        if isinstance(rule, bool):
            result[tool_name] = rule
        else:
            result[tool_name] = {"allowed_decisions": rule.allowed_decisions}
    return result


async def _resolve_subagent_instructions(sa: SubAgentConfig, prompt_manager: PromptManager | None) -> str | None:
    """Resolve subagent instructions, falling back to YAML if Phoenix load fails."""
    instructions = sa.instructions
    if not prompt_manager:
        return instructions
    try:
        content = await prompt_manager.get_prompt_content(sa.name)
        return content.get("content")
    except Exception:
        logger.warning(LogMessage.SUBAGENT_PROMPT_LOAD_FAILED, sa.name)
        return sa.instructions


async def _resolve_subagents(
    config: AgentConfig,
    mcp_tool_loader: McpToolLoader | None = None,
    prompt_manager: PromptManager | None = None,
) -> list | None:
    """Convertit les configs de sous-agents.

    Args:
        config: Configuration de l'agent principal.
        mcp_tool_loader: Loader MCP optionnel pour les sous-agents.

    Returns:
        Liste de dicts de sous-agents ou None.
    """
    if not config.subagents:
        return None
    subagents = []
    for sa in config.subagents:
        local_tools = _resolve_tools_list(sa.tools) if sa.tools else None
        mcp_tools: list = []
        if sa.mcp_servers and mcp_tool_loader:
            mcp_tools = await mcp_tool_loader.load_tools(sa.mcp_servers)
        all_tools = (local_tools or []) + mcp_tools if (local_tools or mcp_tools) else None

        instructions = await _resolve_subagent_instructions(sa, prompt_manager)

        subagents.append(
            {
                "name": sa.name,
                "description": sa.description,
                "system_prompt": instructions,
                "model": sa.model,
                "tools": all_tools,
                "response_format": sa.response_format,
            }
        )
    return subagents


def _resolve_tools_list(tool_paths: list[str]) -> list | None:
    """Helper pour resoudre une liste de tools."""
    if not tool_paths:
        return None
    tools = []
    for tool_path in tool_paths:
        module_path, _, attr_name = tool_path.rpartition(":")
        if module_path and attr_name:
            module = importlib.import_module(module_path)
            tools.append(getattr(module, attr_name))
    return tools or None


def _apply_optional_kwargs(kwargs: dict, config: AgentConfig, store) -> None:
    """Populate optional kwargs from config if their values are set.

    Args:
        kwargs: The kwargs dict passed to ``create_deep_agent``.
        config: Configuration de l'agent.
        store: The store instance (in-memory or Postgres) to wire into ``StoreBackend``.
    """
    backend = _resolve_backend(store)
    if backend:
        kwargs["backend"] = backend
    interrupt_on = _resolve_interrupt_on(config)
    if interrupt_on:
        kwargs["interrupt_on"] = interrupt_on


async def _prepare_agent_namespace(
    store,
    agent_name: str,
    skills: list[str],
    memory: list[str],
) -> tuple[str, list[str]]:
    """Copy selected skills and memories to the agent's namespace in the store.

    The agent namespace follows the pattern:
    - Skills: /agents/{agent_name}/skills/{skill_name}/SKILL.md
    - Memories: /agents/{agent_name}/memories/{filename}

    This ensures SkillsMiddleware only discovers skills explicitly selected
    for this agent, not all skills in the global /skills/ directory.

    Args:
        store: The shared LangGraph BaseStore instance.
        agent_name: Name of the agent.
        skills: List of skill directory paths (e.g. ["/skills/mcp/", "/skills/rag/"]).
        memory: List of memory file paths (e.g. ["/memories/AGENTS.md"]).

    Returns:
        Tuple of (skills_source_path, memory_paths) for create_deep_agent.
    """
    ns = ("filesystem",)
    agent_skills_dir = f"/agents/{agent_name}/skills/"
    agent_memories_dir = f"/agents/{agent_name}/memories/"

    # 1. Cleanup: delete files in agent namespace that are no longer selected
    existing_items = await store.asearch(ns, limit=100)
    selected_skill_names = {s.rstrip("/").split("/")[-1] for s in skills}
    selected_memory_files = {m.split("/")[-1] for m in memory}

    for item in existing_items:
        if item.key.startswith(agent_skills_dir):
            remainder = item.key[len(agent_skills_dir) :]
            skill_name = remainder.split("/")[0] if "/" in remainder else remainder
            if skill_name not in selected_skill_names:
                await store.adelete(ns, item.key)
        elif item.key.startswith(agent_memories_dir):
            filename = item.key[len(agent_memories_dir) :]
            if filename not in selected_memory_files:
                await store.adelete(ns, item.key)

    # 2. Copy selected skills to agent namespace
    for skill_dir in skills:
        skill_name = skill_dir.rstrip("/").split("/")[-1]
        src_path = f"{skill_dir.rstrip('/')}/SKILL.md"
        dst_path = f"{agent_skills_dir}{skill_name}/SKILL.md"
        item = await store.aget(ns, src_path)
        if item is not None:
            await store.aput(ns, dst_path, item.value)

    # 3. Copy selected memories to agent namespace
    new_memory_paths: list[str] = []
    for mem_path in memory:
        filename = mem_path.split("/")[-1]
        dst_path = f"{agent_memories_dir}{filename}"
        item = await store.aget(ns, mem_path)
        if item is not None:
            await store.aput(ns, dst_path, item.value)
        new_memory_paths.append(dst_path)

    return agent_skills_dir, new_memory_paths


async def create_agent_from_config(
    config: AgentConfig,
    mcp_tool_loader: McpToolLoader | None = None,
    prompt_manager: PromptManager | None = None,
):
    """Create a compiled Deep Agent from configuration.

    Args:
        config: Agent configuration.
        mcp_tool_loader: Optional MCP tool loader for loading remote tools.

    Returns:
        Tuple of (compiled agent graph, response_format_model or None).
    """
    logger.info(LogMessage.AGENT_CREATING, config.name, config.model)
    if config.backend.checkpoint_backend == "postgres":
        checkpointer = await _create_postgres_checkpointer()
    else:
        checkpointer = MemorySaver()

    # The store is a global singleton shared between the Store File API and all
    # agents. If Postgres was initialized at startup (by dependencies.py), use
    # that. Otherwise use the shared InMemoryStore. This ensures skills and
    # memories created via the API are visible to agents regardless of the
    # per-agent store_backend setting.
    store = await _get_shared_store()

    local_tools = _resolve_tools(config)
    mcp_tools: list = []
    if config.mcp_servers and mcp_tool_loader:
        logger.info(LogMessage.AGENT_MCP_TOOLS_LOADING, config.name, len(config.mcp_servers))
        mcp_tools = await mcp_tool_loader.load_tools(config.mcp_servers)
        logger.info(LogMessage.AGENT_MCP_TOOLS_LOADED, len(mcp_tools), config.name)
    all_tools = (local_tools or []) + mcp_tools if (local_tools or mcp_tools) else None
    logger.info(LogMessage.AGENT_TOOLS_TOTAL, config.name, len(all_tools) if all_tools else 0)

    system_prompt = await get_system_prompt_from_phoenix(config.name, prompt_manager) if prompt_manager else None

    # Prepare agent namespace: copy selected skills and memories to
    # /agents/{name}/skills/ and /agents/{name}/memories/ so that
    # SkillsMiddleware only loads the selected ones.
    skills_source: str | None = None
    memory_paths: list[str] | None = None
    if config.skills:
        skills_source, memory_paths = await _prepare_agent_namespace(store, config.name, config.skills, config.memory)
    elif config.memory:
        _, memory_paths = await _prepare_agent_namespace(store, config.name, [], config.memory)

    kwargs = {
        "name": config.name,
        "model": config.model,
        "system_prompt": system_prompt if system_prompt else config.system_prompt,
        "tools": all_tools,
        "checkpointer": checkpointer,
        "store": store,
    }

    if skills_source:
        kwargs["skills"] = [skills_source]
    if memory_paths:
        kwargs["memory"] = memory_paths

    _apply_optional_kwargs(kwargs, config, store)

    if config.response_format:
        response_format_model, response_format_dict = _resolve_response_format(config.response_format)
        kwargs["response_format"] = response_format_dict
    else:
        response_format_model = None

    subagents = await _resolve_subagents(config, mcp_tool_loader, prompt_manager)
    if subagents:
        kwargs["subagents"] = subagents
        logger.info(LogMessage.AGENT_SUBAGENTS, config.name, len(subagents))
    try:
        graph = create_deep_agent(**kwargs)
    except Exception:
        logger.exception(LogMessage.AGENT_CREATE_ERROR, config.name)
        raise
    logger.info(LogMessage.AGENT_CREATED, config.name)
    return graph, response_format_model


# helper to get system_prompt from Phoenix
async def get_system_prompt_from_phoenix(agent_name: str, prompt_manager: PromptManager | None = None) -> str | None:
    """Get system_prompt from Phoenix for a given agent name."""
    if not prompt_manager:
        return None
    try:
        content = await prompt_manager.get_prompt_content(agent_name)
        return content.get("content") if content else None
    except Exception:
        return None
