from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.use_cases.load_agent_config import LoadAgentConfigUseCase
from src.dependencies import get_agents_dir, get_load_agent_config_use_case
from src.domain.entities.agent_config import AgentConfig

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("")
async def list_agents(
    use_case: Annotated[LoadAgentConfigUseCase, Depends(get_load_agent_config_use_case)],
    agents_dir: Annotated[str, Depends(get_agents_dir)],
) -> list[AgentConfig]:
    """List all available agent configurations from the agents/ directory.

    Args:
        use_case: Injected LoadAgentConfigUseCase.
        agents_dir: Configured agents directory path.

    Returns:
        A list of AgentConfig for each YAML file found.
    """
    from pathlib import Path

    agents_path = Path(agents_dir)
    configs: list[AgentConfig] = []
    if agents_path.exists():
        for yaml_file in sorted(agents_path.glob("*.yaml")):
            config = use_case.execute(yaml_file)
            configs.append(config)
    return configs


@router.get("/{agent_name}")
async def get_agent(
    agent_name: str,
    use_case: Annotated[LoadAgentConfigUseCase, Depends(get_load_agent_config_use_case)],
    agents_dir: Annotated[str, Depends(get_agents_dir)],
) -> AgentConfig:
    """Load and return a specific agent configuration by name.

    Args:
        agent_name: The agent name (corresponding to the YAML filename without extension).
        use_case: Injected LoadAgentConfigUseCase.
        agents_dir: Configured agents directory path.

    Returns:
        The AgentConfig loaded from the YAML file.

    Raises:
        ConfigNotFoundError: If no YAML file is found for the given agent name.
    """
    from pathlib import Path

    config_path = Path(agents_dir) / f"{agent_name}.yaml"
    return use_case.execute(config_path)
