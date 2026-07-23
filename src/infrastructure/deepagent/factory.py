import importlib
import logging
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, StoreBackend
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel

from src.domain.entities.agent_config import AgentConfig, BackendType, SubAgentConfig
from src.domain.logging.messages import LogMessage
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.prompt_manager import PromptManager
from src.infrastructure.deepagent.schema_utils import schema_to_pydantic_model

logger = logging.getLogger(__name__)


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


def _resolve_backend(config: AgentConfig):
    """Cree le backend selon la config."""
    match config.backend.type:
        case BackendType.STATE:
            return None  # Defaut de create_deep_agent
        case BackendType.FILESYSTEM:
            # virtual_mode=False keeps the historical behaviour (root_dir-bounded
            # persistence without virtual path routing). Specified explicitly to
            # silence the deepagents>=0.6 default-change deprecation warning.
            return FilesystemBackend(
                root_dir=config.backend.root_dir or "./workspace",
                virtual_mode=False,
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


def _apply_optional_kwargs(kwargs: dict, config: AgentConfig) -> None:
    """Populate optional kwargs from config if their values are set."""
    backend = _resolve_backend(config)
    if backend:
        kwargs["backend"] = backend
    interrupt_on = _resolve_interrupt_on(config)
    if interrupt_on:
        kwargs["interrupt_on"] = interrupt_on
    if config.memory:
        kwargs["memory"] = config.memory
    if config.skills:
        kwargs["skills"] = config.skills


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
    checkpointer = MemorySaver()
    store = InMemoryStore()

    local_tools = _resolve_tools(config)
    mcp_tools: list = []
    if config.mcp_servers and mcp_tool_loader:
        logger.info(LogMessage.AGENT_MCP_TOOLS_LOADING, config.name, len(config.mcp_servers))
        mcp_tools = await mcp_tool_loader.load_tools(config.mcp_servers)
        logger.info(LogMessage.AGENT_MCP_TOOLS_LOADED, len(mcp_tools), config.name)
    all_tools = (local_tools or []) + mcp_tools if (local_tools or mcp_tools) else None
    logger.info(LogMessage.AGENT_TOOLS_TOTAL, config.name, len(all_tools) if all_tools else 0)

    system_prompt = await get_system_prompt_from_phoenix(config.name, prompt_manager) if prompt_manager else None

    kwargs = {
        "name": config.name,
        "model": config.model,
        "system_prompt": system_prompt if system_prompt else config.system_prompt,
        "tools": all_tools,
        "middleware": [],
        "checkpointer": checkpointer,
        "store": store,
    }

    _apply_optional_kwargs(kwargs, config)

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
