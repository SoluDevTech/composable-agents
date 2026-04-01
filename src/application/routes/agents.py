import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.use_cases.load_agent_config import LoadAgentConfigUseCase
from src.dependencies import get_agents_dir, get_load_agent_config_use_case
from src.domain.entities.agent_config import AgentConfig

logger = logging.getLogger("composable-agents")

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("")
async def list_agents(
    use_case: Annotated[LoadAgentConfigUseCase, Depends(get_load_agent_config_use_case)],
    agents_dir: Annotated[str, Depends(get_agents_dir)],
) -> list[AgentConfig]:
    agents_path = Path(agents_dir)
    configs: list[AgentConfig] = []
    if agents_path.exists():
        for yaml_file in sorted(agents_path.glob("*.yaml")):
            config = use_case.execute(yaml_file)
            configs.append(config)
    logger.info("Listed %d agents from %s", len(configs), agents_dir)
    return configs


@router.get("/{agent_name}")
async def get_agent(
    agent_name: str,
    use_case: Annotated[LoadAgentConfigUseCase, Depends(get_load_agent_config_use_case)],
    agents_dir: Annotated[str, Depends(get_agents_dir)],
) -> AgentConfig:
    logger.debug("Loading agent config: %s", agent_name)
    config_path = Path(agents_dir) / f"{agent_name}.yaml"
    return use_case.execute(config_path)
