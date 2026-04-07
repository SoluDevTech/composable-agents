import hashlib
import importlib
import json
import logging
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, StoreBackend
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import Field as PydanticField
from pydantic import create_model

from src.domain.entities.agent_config import AgentConfig, BackendType
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger("composable-agents")

STRUCTURED_OUTPUT_INSTRUCTION = (
    "\n\nYou MUST use the 'structured_response' tool to return your final answer in the expected structured format."
)


_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _create_response_tool(schema: dict[str, Any]) -> StructuredTool:
    """Create a StructuredTool from a JSON Schema dict for structured output.

    Builds a Pydantic model dynamically so the LLM knows the expected fields.
    A sync func is required because deepagents invokes subagent tools synchronously.
    """
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    field_definitions: dict[str, Any] = {}
    for field_name, prop in properties.items():
        python_type = _JSON_TYPE_MAP.get(prop.get("type", "string"), str)
        description = prop.get("description", "")
        if field_name in required_fields:
            field_definitions[field_name] = (python_type, PydanticField(description=description))
        else:
            field_definitions[field_name] = (python_type | None, PydanticField(default=None, description=description))

    schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:8]
    args_model = create_model(f"StructuredResponseArgs_{schema_hash}", **field_definitions)

    def _return_structured(**kwargs: Any) -> str:
        return json.dumps(kwargs)

    return StructuredTool.from_function(
        func=_return_structured,
        name="structured_response",
        description="Return your final answer using this tool with the expected structured format.",
        args_schema=args_model,
    )


def _resolve_tools(config: AgentConfig) -> list | None:
    """Charge les tools depuis leurs chemins Python (module:attribute)."""
    if not config.tools:
        return None
    tools = []
    for tool_path in config.tools:
        module_path, _, attr_name = tool_path.rpartition(":")
        if not module_path or not attr_name:
            logger.error(f"Invalid tool format '{tool_path}'")
            raise ValueError(
                f"Invalid tool format '{tool_path}'. "
                f"Expected: 'module.path:tool_name' (e.g., 'mypackage.tools:my_tool')"
            )
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            logger.exception(f"Module not found for tool '{tool_path}'")
            raise ValueError(f"Module not found for tool '{tool_path}': {e}") from e

        if not hasattr(module, attr_name):
            available = [a for a in dir(module) if not a.startswith("_")]
            logger.error(f"Attribute '{attr_name}' not found in '{module_path}'")
            raise ValueError(f"Attribute '{attr_name}' not found in '{module_path}'. Available: {available}")
        tools.append(getattr(module, attr_name))
    return tools


def _resolve_backend(config: AgentConfig):
    """Cree le backend selon la config."""
    match config.backend.type:
        case BackendType.STATE:
            return None  # Defaut de create_deep_agent
        case BackendType.FILESYSTEM:
            return FilesystemBackend(root_dir=config.backend.root_dir or "./workspace")
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

        instructions = sa.instructions
        if prompt_manager:
            try:
                content = await prompt_manager.get_prompt_content(sa.name)
                instructions = content.get("content")
            except Exception:
                logger.warning(f"Could not load system prompt for sub-agent '{sa.name}' from Phoenix, using YAML instructions if available.")
                instructions = sa.instructions

        if sa.response_format:
            response_tool = _create_response_tool(sa.response_format)
            all_tools = (all_tools or []) + [response_tool]
            instructions = (instructions or "") + STRUCTURED_OUTPUT_INSTRUCTION

        subagents.append(
            {
                "name": sa.name,
                "description": sa.description,
                "system_prompt": instructions,
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
    prompt_manager: PromptManager | None = None,
):
    """Create a compiled Deep Agent from configuration.

    Args:
        config: Agent configuration.
        mcp_tool_loader: Optional MCP tool loader for loading remote tools.

    Returns:
        The compiled agent ready for execution.
    """
    logger.info("Creating agent '%s' (model=%s)", config.name, config.model)
    checkpointer = MemorySaver()
    store = InMemoryStore()
    interrupt_on = _resolve_interrupt_on(config)
    system_prompt = None

    local_tools = _resolve_tools(config)
    mcp_tools: list = []
    if config.mcp_servers and mcp_tool_loader:
        logger.info("Loading MCP tools for agent '%s' (%d servers)", config.name, len(config.mcp_servers))
        mcp_tools = await mcp_tool_loader.load_tools(config.mcp_servers)
        logger.info("Loaded %d MCP tools for agent '%s'", len(mcp_tools), config.name)
    all_tools = (local_tools or []) + mcp_tools if (local_tools or mcp_tools) else None
    logger.debug("Agent '%s' tools: %d total", config.name, len(all_tools) if all_tools else 0)

    if prompt_manager:
        system_prompt = await get_system_prompt_from_phoenix(config.name, prompt_manager)

    kwargs = {
        "name": config.name,
        "model": config.model,
        # Fall back to YAML system_prompt
        "system_prompt": system_prompt if system_prompt else config.system_prompt,
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

    if config.response_format:
        kwargs["response_format"] = ProviderStrategy(config.response_format)

    subagents = await _resolve_subagents(config, mcp_tool_loader, prompt_manager)
    if subagents:
        kwargs["subagents"] = subagents
        logger.info("Agent '%s' has %d subagents", config.name, len(subagents))

    graph = create_deep_agent(**kwargs)
    logger.info("Agent '%s' created successfully", config.name)
    return graph


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
