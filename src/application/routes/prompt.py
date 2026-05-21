import logging

from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError

from src.application.requests.prompt import (
    CreatePromptRequest,
    UpdatePromptRequest,
)
from src.application.use_cases.create_prompt import CreatePromptUseCase
from src.application.use_cases.get_prompt import GetPromptUseCase
from src.application.use_cases.update_prompt import UpdatePromptUseCase
from src.dependencies import get_prompt_manager
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _handle_http_error(e: Exception, identifier: str | None = None) -> HTTPException:
    """Map exceptions to appropriate HTTP status codes."""
    if isinstance(e, ValueError) and "not found" in str(e).lower():
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, HTTPStatusError):
        if e.response.status_code == 404:
            return HTTPException(status_code=404, detail=f"Prompt not found: {identifier}")
        if e.response.status_code == 409:
            return HTTPException(status_code=409, detail=f"Prompt already exists: {identifier}")
        if e.response.status_code == 400:
            return HTTPException(status_code=400, detail=str(e))
    if isinstance(e, ValueError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail=str(e))


@router.post("/create", status_code=201)
async def create_prompt(
    request: CreatePromptRequest,
    prompt_manager: PromptManager = Depends(get_prompt_manager),
):
    """Create a new prompt."""
    use_case = CreatePromptUseCase(prompt_manager)
    try:
        logger.info("Creating prompt: %s", request.identifier)
        content_dicts = [msg.model_dump() for msg in request.content]
        prompt = await use_case.execute(
            identifier=request.identifier,
            content=content_dicts,
            model_name=request.model_name,
            description=request.description,
            tags=request.tags,
            metadata=request.metadata,
        )
        logger.info("Prompt created: %s", request.identifier)
        return {"status": "success", "prompt": prompt}
    except Exception:
        logger.exception("Error creating prompt '%s'", request.identifier)
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
        logger.exception("Error getting prompt '%s'", identifier)
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
        logger.exception("Error updating prompt '%s'", identifier)
        raise
