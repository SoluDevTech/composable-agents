import logging

from fastapi import APIRouter, Depends, HTTPException

from src.application.requests.prompt import (
    CreatePromptRequest,
    UpdatePromptRequest,
)
from src.application.use_cases.create_prompt import CreatePromptUseCase
from src.application.use_cases.get_prompt import GetPromptUseCase
from src.application.use_cases.update_prompt import UpdatePromptUseCase
from src.dependencies import get_prompt_manager  # We'll add this
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger("composable-agents")

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("/create")
async def create_prompt(
    request: CreatePromptRequest,
    prompt_manager: PromptManager = Depends(get_prompt_manager),
):
    """Create a new prompt."""
    use_case = CreatePromptUseCase(prompt_manager)
    try:
        prompt = await use_case.execute(
            identifier=request.identifier,
            content=request.content,
            model_name=request.model_name,
            description=request.description,
            tags=request.tags,
            metadata=request.metadata,
        )
        return {"status": "success", "prompt": prompt}
    except Exception as e:
        logger.error(f"Error creating prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        logger.error(f"Error getting prompt: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/update/{identifier}")
async def update_prompt(
    identifier: str,
    request: UpdatePromptRequest,
    prompt_manager: PromptManager = Depends(get_prompt_manager),
):
    """Update a prompt."""
    use_case = UpdatePromptUseCase(prompt_manager)
    try:
        prompt = await use_case.execute(
            identifier=identifier,
            content=request.content,
            model_name=request.model_name,
            description=request.description,
            metadata=request.metadata,
        )
        return {"status": "success", "prompt": prompt}
    except Exception as e:
        logger.error(f"Error updating prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
