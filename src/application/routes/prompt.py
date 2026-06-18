import logging

from fastapi import APIRouter, Depends

from src.application.requests.prompt import (
    CreatePromptRequest,
    UpdatePromptRequest,
)
from src.application.use_cases.create_prompt import CreatePromptUseCase
from src.application.use_cases.get_prompt import GetPromptUseCase
from src.application.use_cases.update_prompt import UpdatePromptUseCase
from src.dependencies import get_prompt_manager
from src.domain.logging.messages import LogMessage
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("/create", status_code=201)
async def create_prompt(
    request: CreatePromptRequest,
    prompt_manager: PromptManager = Depends(get_prompt_manager),
):
    """Create a new prompt."""
    use_case = CreatePromptUseCase(prompt_manager)
    try:
        logger.info(LogMessage.PROMPT_CREATING, request.identifier)
        content_dicts = [msg.model_dump() for msg in request.content]
        prompt = await use_case.execute(
            identifier=request.identifier,
            content=content_dicts,
            model_name=request.model_name,
            description=request.description,
            tags=request.tags,
            metadata=request.metadata,
        )
        logger.info(LogMessage.PROMPT_CREATED, request.identifier)
        return {"status": "success", "prompt": prompt}
    except Exception:
        logger.exception(LogMessage.PROMPT_CREATE_ERROR, request.identifier)
        raise


@router.get("/get/{identifier}")
async def get_prompt(
    identifier: str,
    version_id: str | None = None,
    tag: str | None = None,
    prompt_manager: PromptManager = Depends(get_prompt_manager),
):
    """Get a prompt."""
    use_case = GetPromptUseCase(prompt_manager)
    try:
        prompt = await use_case.execute(
            identifier=identifier,
            version_id=version_id,
            tag=tag,
        )
        return {"status": "success", "prompt": prompt}
    except Exception:
        logger.exception(LogMessage.PROMPT_GET_ERROR, identifier)
        raise


@router.put("/update/{identifier}")
async def update_prompt(
    identifier: str,
    request: UpdatePromptRequest,
    prompt_manager: PromptManager = Depends(get_prompt_manager),
):
    """Update a prompt."""
    use_case = UpdatePromptUseCase(prompt_manager)
    try:
        content_dicts = [msg.model_dump() for msg in request.content] if request.content else None
        prompt = await use_case.execute(
            identifier=identifier,
            content=content_dicts,
            model_name=request.model_name,
            description=request.description,
            metadata=request.metadata,
        )
        return {"status": "success", "prompt": prompt}
    except Exception:
        logger.exception(LogMessage.PROMPT_UPDATE_ERROR, identifier)
        raise
