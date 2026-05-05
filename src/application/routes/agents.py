import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from src.application.use_cases.create_agent_config import CreateAgentConfigUseCase
from src.application.use_cases.delete_agent_config import DeleteAgentConfigUseCase
from src.application.use_cases.get_agent_config import GetAgentConfigUseCase
from src.application.use_cases.list_agent_configs import ListAgentConfigsUseCase
from src.application.use_cases.update_agent_config import UpdateAgentConfigUseCase
from src.dependencies import (
    get_create_agent_config_use_case,
    get_delete_agent_config_use_case,
    get_get_agent_config_use_case,
    get_list_agent_configs_use_case,
    get_update_agent_config_use_case,
)
from src.domain.entities.agent_config import AgentConfig
from src.domain.entities.agent_config_metadata import AgentConfigMetadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

AGENT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,98}[a-zA-Z0-9]$")
MAX_UPLOAD_SIZE = 1024 * 1024  # 1 MB


def _validate_agent_name(name: str) -> None:
    if not AGENT_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent name '{name}'. Must match pattern: alphanumeric, dots, hyphens, underscores, 2-100 chars.",
        )


async def _read_yaml_upload(file: UploadFile) -> str:
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE} bytes.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 encoded YAML.") from e


@router.get("", response_model=list[AgentConfigMetadata])
async def list_agents(
    use_case: Annotated[ListAgentConfigsUseCase, Depends(get_list_agent_configs_use_case)],
) -> list[AgentConfigMetadata]:
    """List all agent configuration metadata."""
    return await use_case.execute()


@router.get("/{agent_name}", response_model=AgentConfig)
async def get_agent(
    agent_name: str,
    use_case: Annotated[GetAgentConfigUseCase, Depends(get_get_agent_config_use_case)],
) -> AgentConfig:
    """Retrieve a single agent configuration by name."""
    _validate_agent_name(agent_name)
    return await use_case.execute(name=agent_name)


@router.post("", response_model=AgentConfig, status_code=status.HTTP_201_CREATED)
async def create_agent(
    use_case: Annotated[CreateAgentConfigUseCase, Depends(get_create_agent_config_use_case)],
    agent_name: str = Form(...),
    file: UploadFile = File(...),
) -> AgentConfig:
    """Create a new agent configuration from an uploaded YAML file."""
    _validate_agent_name(agent_name)
    yaml_content = await _read_yaml_upload(file)
    return await use_case.execute(name=agent_name, yaml_content=yaml_content)


@router.put("/{agent_name}", response_model=AgentConfig)
async def update_agent(
    agent_name: str,
    use_case: Annotated[UpdateAgentConfigUseCase, Depends(get_update_agent_config_use_case)],
    file: UploadFile = File(...),
) -> AgentConfig:
    """Update an existing agent configuration from an uploaded YAML file."""
    _validate_agent_name(agent_name)
    yaml_content = await _read_yaml_upload(file)
    return await use_case.execute(name=agent_name, yaml_content=yaml_content)


@router.delete("/{agent_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_name: str,
    use_case: Annotated[DeleteAgentConfigUseCase, Depends(get_delete_agent_config_use_case)],
) -> None:
    """Delete an agent configuration."""
    _validate_agent_name(agent_name)
    await use_case.execute(name=agent_name)
