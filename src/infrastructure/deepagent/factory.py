import importlib

from deepagents import create_deep_agent
from deepagents.backends import StoreBackend, FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from src.domain.entities.agent_config import AgentConfig, BackendType
from src.domain.ports.mcp_tool_loader import McpToolLoader


def _resolve_tools(config: AgentConfig) -> list | None:
    """Charge les tools depuis leurs chemins Python (module:attribute)."""
    if not config.tools:
        return None
    tools = []
    for tool_path in config.tools:
        module_path, _, attr_name = tool_path.rpartition(":")
        if not module_path or not attr_name:
            raise ValueError(
                f"Format de tool invalide '{tool_path}'. "
                f"Attendu: 'module.path:tool_name' (ex: 'mypackage.tools:my_tool')"
            )
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            raise ValueError(f"Module introuvable pour le tool '{tool_path}': {e}") from e

        if not hasattr(module, attr_name):
            available = [a for a in dir(module) if not a.startswith("_")]
            raise ValueError(
                f"Attribut '{attr_name}' introuvable dans '{module_path}'. Disponibles: {available}"
            )
        tools.append(getattr(module, attr_name))
    return tools


def _resolve_backend(config: AgentConfig):
    """Cree le backend selon la config."""
    match config.backend.type:
        case BackendType.STATE:
            return None  # Defaut de create_deep_agent
        case BackendType.FILESYSTEM:
            return FilesystemBackend(
                root_dir=config.backend.root_dir or "./workspace"
            )
        case BackendType.STORE:
            return lambda rt: StoreBackend(rt)
        case BackendType.COMPOSITE:
            return None  # Fallback, necessite config avancee


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


async def _resolve_subagents(
    config: AgentConfig,
    mcp_tool_loader: McpToolLoader | None = None,
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
        subagents.append(
            {
                "name": sa.name,
                "description": sa.description,
                "system_prompt": sa.instructions,
                "model": sa.model,
                "tools": all_tools,
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


async def create_agent_from_config(
    config: AgentConfig,
    mcp_tool_loader: McpToolLoader | None = None,
):
    """Cree un Deep Agent compile a partir d'une configuration.

    Args:
        config: Configuration de l'agent.
        mcp_tool_loader: Loader MCP optionnel pour charger des outils distants.

    Returns:
        L'agent compile pret a l'execution.
    """
    checkpointer = MemorySaver()
    store = InMemoryStore()
    interrupt_on = _resolve_interrupt_on(config)

    local_tools = _resolve_tools(config)
    mcp_tools: list = []
    if config.mcp_servers and mcp_tool_loader:
        mcp_tools = await mcp_tool_loader.load_tools(config.mcp_servers)
    all_tools = (local_tools or []) + mcp_tools if (local_tools or mcp_tools) else None

    kwargs = {
        "name": config.name,
        "model": config.model,
        "system_prompt": config.system_prompt,
        "tools": all_tools,
        "middleware": [],
        "checkpointer": checkpointer,
        "store": store,
    }

    backend = _resolve_backend(config)
    if backend:
        kwargs["backend"] = backend

    if interrupt_on:
        kwargs["interrupt_on"] = interrupt_on

    if config.memory:
        kwargs["memory"] = config.memory

    if config.skills:
        kwargs["skills"] = config.skills

    subagents = await _resolve_subagents(config, mcp_tool_loader)
    if subagents:
        kwargs["subagents"] = subagents

    return create_deep_agent(**kwargs)
