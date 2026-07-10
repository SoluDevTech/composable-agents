import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.requests.prompt import (
    CreatePromptRequest,
    UpdatePromptRequest,
)
from src.application.responses.prompt import PromptResponse, PromptVersionResponse
from src.application.use_cases.create_prompt import CreatePromptUseCase
from src.application.use_cases.get_prompt import GetPromptUseCase
from src.application.use_cases.update_prompt import UpdatePromptUseCase
from src.dependencies import (
    get_create_prompt_use_case,
    get_get_prompt_use_case,
    get_update_prompt_use_case,
)
from src.domain.logging.messages import LogMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])


@router.post("/create", status_code=201, response_model=PromptVersionResponse)
async def create_prompt(
    request: CreatePromptRequest,
    use_case: Annotated[CreatePromptUseCase, Depends(get_create_prompt_use_case)],
) -> PromptVersionResponse:
    """Create a new prompt."""
    try:
        logger.info(LogMessage.PROMPT_CREATING, request.identifier)
        content_dicts = [msg.model_dump() for msg in request.content]
        result = await use_case.execute(
            identifier=request.identifier,
            content=content_dicts,
            model_name=request.model_name,
            description=request.description,
            tags=request.tags,
            metadata=request.metadata,
        )
        logger.info(LogMessage.PROMPT_CREATED, request.identifier)
        return PromptVersionResponse(status="success", prompt_version=result)
    except Exception:
        logger.exception(LogMessage.PROMPT_CREATE_ERROR, request.identifier)
        raise


@router.get("/get/{identifier}", response_model=PromptResponse)
async def get_prompt(
    identifier: str,
    use_case: Annotated[GetPromptUseCase, Depends(get_get_prompt_use_case)],
    version_id: str | None = None,
    tag: str | None = None,
) -> PromptResponse:
    """Get a prompt."""
    try:
        result = await use_case.execute(
            identifier=identifier,
            version_id=version_id,
            tag=tag,
        )
        return PromptResponse(status="success", prompt=result)
    except Exception:
        logger.exception(LogMessage.PROMPT_GET_ERROR, identifier)
        raise


@router.put("/update/{identifier}", response_model=PromptVersionResponse)
async def update_prompt(
    identifier: str,
    request: UpdatePromptRequest,
    use_case: Annotated[UpdatePromptUseCase, Depends(get_update_prompt_use_case)],
) -> PromptVersionResponse:
    """Update a prompt."""
    try:
        content_dicts = [msg.model_dump() for msg in request.content] if request.content else None
        result = await use_case.execute(
            identifier=identifier,
            content=content_dicts,
            model_name=request.model_name,
            description=request.description,
            metadata=request.metadata,
        )
        return PromptVersionResponse(status="success", prompt_version=result)
    except Exception:
        logger.exception(LogMessage.PROMPT_UPDATE_ERROR, identifier)
        raise
