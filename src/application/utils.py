"""Utility functions for agent configuration operations."""

from datetime import UTC, datetime

from src.domain.entities.agent_config import AgentConfig
from src.domain.entities.agent_config_metadata import AgentConfigMetadata


def create_agent_metadata(
    name: str, config: AgentConfig, is_builtin: bool = False
) -> AgentConfigMetadata:
    """Create agent configuration metadata.

    Args:
        name: Agent name.
        config: Parsed agent configuration.
        is_builtin: Whether this is a built-in agent.

    Returns:
        AgentConfigMetadata instance with current timestamp.
    """
    now = datetime.now(UTC)
    return AgentConfigMetadata(
        name=name,
        model=config.model,
        minio_path=f"{name}.yaml",
        is_builtin=is_builtin,
        created_at=now,
        updated_at=now,
    )
