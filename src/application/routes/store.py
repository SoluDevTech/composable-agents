"""FastAPI routes for managing files in the LangGraph store.

Endpoints:
    GET    /api/v1/store/files          — list file paths (optional ``prefix`` query param)
    GET    /api/v1/store/files/{path}    — get file content (200 or 404)
    PUT    /api/v1/store/files/{path}    — create or replace a file (200)
    DELETE /api/v1/store/files/{path}    — delete a file (204)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from src.application.use_cases.manage_store_file import (
    DeleteStoreFileUseCase,
    GetStoreFileUseCase,
    ListStoreFilePreviewsUseCase,
    ListStoreFilesUseCase,
    PutStoreFileUseCase,
)
from src.dependencies import (
    get_delete_store_file_use_case,
    get_get_store_file_use_case,
    get_list_store_file_previews_use_case,
    get_list_store_files_use_case,
    get_put_store_file_use_case,
)
from src.domain.errors.store_file import StoreFileNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/store", tags=["store"])


def _normalize_path(path: str) -> str:
    """Ensure the path starts with a forward slash and reject path traversal."""
    normalized = path if path.startswith("/") else f"/{path}"
    if ".." in normalized:
        raise StoreFileNotFoundError(f"Invalid path: {path}")
    return normalized


class StoreFileResponse(BaseModel):
    """Response DTO for a store file."""

    path: str
    content: str


class StoreFilePreviewResponse(BaseModel):
    """Response DTO for a store file with a truncated preview."""

    path: str
    preview: str


class StoreFilePutRequest(BaseModel):
    """Request body for creating or replacing a store file."""

    content: str = Field(..., max_length=10_000_000)


@router.get("/files", response_model=list[str], status_code=status.HTTP_200_OK)
async def list_store_files(
    use_case: Annotated[ListStoreFilesUseCase, Depends(get_list_store_files_use_case)],
    prefix: str = Query(default="/", description="Path prefix to filter files by."),
) -> list[str]:
    """List file paths in the store, optionally filtered by prefix.

    Args:
        use_case: Injected list files use case.
        prefix: Path prefix to filter on (default ``"/"`` = all files).

    Returns:
        A list of file path strings.
    """
    return await use_case.execute(prefix=prefix)


@router.get("/files/previews", response_model=list[StoreFilePreviewResponse], status_code=status.HTTP_200_OK)
async def list_store_file_previews(
    use_case: Annotated[ListStoreFilePreviewsUseCase, Depends(get_list_store_file_previews_use_case)],
    prefix: str = Query(default="/", description="Path prefix to filter files by."),
    chars: int = Query(default=300, ge=1, le=10000, description="Max characters per preview."),
) -> list[StoreFilePreviewResponse]:
    """List files with a truncated content preview.

    Returns one ``StoreFilePreviewResponse`` per matching file, containing the
    first ``chars`` characters of the file content. This avoids N+1 fetches
    when a client needs to display previews (e.g. memory cards or skill names).
    """
    previews = await use_case.execute(prefix=prefix, preview_chars=chars)
    return [StoreFilePreviewResponse(path=p.path, preview=p.preview) for p in previews]


@router.get("/files/{path:path}", response_model=StoreFileResponse, status_code=status.HTTP_200_OK)
async def get_store_file(
    path: str,
    use_case: Annotated[GetStoreFileUseCase, Depends(get_get_store_file_use_case)],
) -> StoreFileResponse:
    """Retrieve a single file by path.

    Args:
        path: The file path (captured from the URL, no leading slash).
        use_case: Injected get file use case.

    Returns:
        A ``StoreFileResponse`` with the path and content.

    Raises:
        StoreFileNotFoundError: If the file does not exist in the store.
    """
    content = await use_case.execute(path=_normalize_path(path))
    if content is None:
        raise StoreFileNotFoundError(f"File not found: {path}")
    return StoreFileResponse(path=_normalize_path(path), content=content)


@router.put("/files/{path:path}", response_model=StoreFileResponse, status_code=status.HTTP_200_OK)
async def put_store_file(
    path: str,
    body: StoreFilePutRequest,
    use_case: Annotated[PutStoreFileUseCase, Depends(get_put_store_file_use_case)],
) -> StoreFileResponse:
    """Create or replace a file in the store.

    Args:
        path: The file path (captured from the URL, no leading slash).
        body: Request body containing the file content.
        use_case: Injected put file use case.

    Returns:
        A ``StoreFileResponse`` with the path and stored content.
    """
    normalized = _normalize_path(path)
    content = await use_case.execute(path=normalized, content=body.content)
    return StoreFileResponse(path=normalized, content=content)


@router.delete("/files/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_store_file(
    path: str,
    use_case: Annotated[DeleteStoreFileUseCase, Depends(get_delete_store_file_use_case)],
) -> None:
    """Delete a file from the store.

    Args:
        path: The file path (captured from the URL, no leading slash).
        use_case: Injected delete file use case.
    """
    await use_case.execute(path=_normalize_path(path))


@router.get("/skills/{skill_name}/usage", response_model=list[str], status_code=status.HTTP_200_OK)
async def get_skill_usage(
    skill_name: str,
    use_case: Annotated[ListStoreFilesUseCase, Depends(get_list_store_files_use_case)],
) -> list[str]:
    """List all agents that have a copy of the given skill.

    Scans the store for paths matching /agents/*/skills/{skill_name}/SKILL.md
    and returns the sorted list of agent names.

    Args:
        skill_name: Name of the skill to check usage for.
        use_case: Injected list files use case.

    Returns:
        A sorted list of agent names that have this skill in their namespace.
    """
    all_files = await use_case.execute(prefix="/agents/")
    agents = set()
    for path in all_files:
        if f"/skills/{skill_name}/" in path:
            parts = path.split("/")
            if len(parts) >= 3 and parts[1] == "agents":
                agents.add(parts[2])
    return sorted(agents)
