"""Shared helpers for subagent ``agent_ref`` validation and dependent invalidation."""

import logging
from collections.abc import Awaitable, Callable

import yaml  # type: ignore[import-untyped]

from src.domain.entities.agent_config import AgentConfig
from src.domain.errors.config import ConfigError
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


async def validate_subagent_refs(
    config: AgentConfig,
    exists_fn: Callable[[str], Awaitable[bool]],
) -> None:
    """Validate subagent ``agent_ref`` references against the repository.

    Raises ``ConfigError`` on self-reference or when a referenced agent
    does not exist.

    Args:
        config: The agent configuration whose subagents are checked.
        exists_fn: Async callable returning ``True`` when the named agent
            exists in the repository.
    """
    for sa in config.subagents:
        if sa.agent_ref is None:
            continue
        if sa.agent_ref == config.name:
            raise ConfigError(
                f"Subagent '{sa.name}' references its own agent '{config.name}' (self-reference is not allowed)."
            )
        if not await exists_fn(sa.agent_ref):
            raise ConfigError(
                f"Subagent '{sa.name}' references unknown agent '{sa.agent_ref}'."
            )


async def invalidate_dependent_agents(
    config_store: AgentConfigStore,
    agent_registry: AgentRegistry,
    agent_name: str,
) -> None:
    """Invalidate cached runners of agents that reference ``agent_name`` via subagent ``agent_ref``.

    Scans every stored YAML, parses it with ``yaml.safe_load`` (lightweight — full
    AgentConfig validation is not needed here) and looks for subagents whose
    ``agent_ref`` equals ``agent_name``. The ``agent_name`` itself is not invalidated
    a second time (the caller is expected to have already invalidated it).

    Corrupted or unparseable YAMLs are logged and skipped so a single bad config
    cannot prevent invalidation of the rest.

    Args:
        config_store: Store exposing all persisted YAML configs.
        agent_registry: Registry whose cached runners must be invalidated.
        agent_name: Name of the agent whose dependents must be invalidated.
    """
    try:
        all_names = await config_store.list_all()
    except Exception:
        logger.warning(
            "Failed to list stored agent configs during dependent invalidation for '%s'",
            agent_name,
        )
        return

    for other_name in all_names:
        if other_name == agent_name:
            continue
        try:
            yaml_content = await config_store.get(other_name)
            data = yaml.safe_load(yaml_content) or {}
            if not isinstance(data, dict):
                continue
            subagents = data.get("subagents") or []
            if not isinstance(subagents, list):
                continue
            for sa in subagents:
                if isinstance(sa, dict) and sa.get("agent_ref") == agent_name:
                    await agent_registry.invalidate(other_name)
                    break
        except Exception:
            logger.warning(
                "Failed to parse YAML for agent '%s' during dependent invalidation",
                other_name,
            )
            continue
