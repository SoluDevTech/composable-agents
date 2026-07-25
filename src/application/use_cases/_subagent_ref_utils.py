"""Shared helpers for subagent ``agent_ref`` validation and dependent invalidation."""

import logging

import yaml  # type: ignore[import-untyped]

from src.domain.entities.agent_config import AgentConfig
from src.domain.errors.config import ConfigError
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


async def validate_subagent_refs(
    config: AgentConfig,
    repository: AgentConfigRepository,
) -> None:
    """Validate subagent ``agent_ref`` references against the metadata repository.

    The metadata repository is the single source of truth for "does this agent
    exist?" — injecting the port (rather than a bound ``exists`` callable) keeps
    the use case decoupled from any one adapter's notion of existence and avoids
    drift if the store/repository split is refactored later.

    Raises ``ConfigError`` on self-reference or when a referenced agent
    does not exist.

    Args:
        config: The agent configuration whose subagents are checked.
        repository: Metadata repository used to confirm referenced agents exist.
    """
    for sa in config.subagents:
        if sa.agent_ref is None:
            continue
        if sa.agent_ref == config.name:
            raise ConfigError(
                f"Subagent '{sa.name}' references its own agent '{config.name}' (self-reference is not allowed)."
            )
        if not await repository.exists(sa.agent_ref):
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

    Corrupted or unparseable YAMLs are logged at ``ERROR`` level (with the
    exception) and skipped so a single bad config cannot prevent invalidation of
    the rest. After the loop, a summary error lists every agent that could not be
    inspected so the failure surface is observable — not silently swallowed.

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
            exc_info=True,
        )
        return

    failed_agents: list[str] = []

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
            logger.error(
                "Failed to parse YAML for agent '%s' during dependent invalidation of '%s'",
                other_name,
                agent_name,
                exc_info=True,
            )
            failed_agents.append(other_name)
            continue

    if failed_agents:
        logger.error(
            "Dependent invalidation for '%s' skipped %d agent(s) with parse errors: %s",
            agent_name,
            len(failed_agents),
            ", ".join(failed_agents),
        )
