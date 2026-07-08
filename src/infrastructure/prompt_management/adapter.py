import asyncio
import logging
import os
import time
from collections import OrderedDict
from typing import Any

import httpx
from phoenix.client import Client
from phoenix.client.resources.prompts import PromptVersion as PhoenixPromptVersion
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.domain.entities.prompt import Prompt, PromptVersion
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.prompt import (
    PromptAlreadyExistsError,
    PromptManagerUnavailableError,
    PromptNotFoundError,
)
from src.domain.logging.messages import LogMessage
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

# Retry config
_RETRY_ATTEMPTS = 3
_RETRY_MIN_WAIT = 1
_RETRY_MAX_WAIT = 10

_phoenix_retry = retry(
    stop=stop_after_attempt(_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=_RETRY_MIN_WAIT, max=_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)

# Domain exceptions that must propagate without being wrapped.
_PROPAGATED_ERRORS = (PromptNotFoundError, PromptManagerUnavailableError, PromptAlreadyExistsError)


def _wrap_phoenix_error(operation: str, identifier: str, e: Exception) -> Exception:
    """Convert raw Phoenix/httpx exceptions to domain exceptions.

    Infrastructure never defines its own error classes: it only raises the
    domain exceptions declared in ``src/domain/exceptions.py``.
    """
    if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
        return PromptManagerUnavailableError(
            ErrorMessage.PROMPT_MANAGER_UNAVAILABLE.format(
                operation=operation, identifier=identifier, error=e
            )
        )
    if isinstance(e, httpx.HTTPStatusError):
        status_code = e.response.status_code
        if status_code == 404:
            return PromptNotFoundError(ErrorMessage.PROMPT_NOT_FOUND.format(identifier=identifier))
        if status_code == 409:
            return PromptAlreadyExistsError(ErrorMessage.PROMPT_ALREADY_EXISTS.format(identifier=identifier))
        if status_code >= 500:
            return PromptManagerUnavailableError(
                ErrorMessage.PROMPT_MANAGER_SERVER_ERROR.format(
                    status_code=status_code, operation=operation, identifier=identifier
                )
            )
    return e


def _extract_messages(phoenix_prompt: Any) -> list[dict[str, str]]:
    """Extract normalized role/content messages from a Phoenix prompt version."""
    template = getattr(phoenix_prompt, "_template", {})
    raw_messages = template.get("messages", []) if isinstance(template, dict) else []

    messages: list[dict[str, str]] = []
    for msg in raw_messages:
        role = msg.get("role", "")
        raw_content = msg.get("content", "")
        if isinstance(raw_content, list):
            text = " ".join(
                block.get("text", "") for block in raw_content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            text = str(raw_content)
        messages.append({"role": role, "content": text})
    return messages


class _AsyncTTLCache:
    """Simple manual async cache with TTL and maxsize, guarded by an asyncio.Lock.

    Replaces cachetools.TTLCache + @cached for async functions, without adding
    the async_lru dependency.
    """

    def __init__(self, maxsize: int = 10, ttl: float = 300) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._store: OrderedDict[tuple, tuple[Any, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: tuple) -> Any:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                return None
            # Refresh LRU ordering.
            self._store.move_to_end(key)
            return value

    async def set(self, key: tuple, value: Any) -> None:
        async with self._lock:
            self._store[key] = (value, time.monotonic() + self._ttl)
            self._store.move_to_end(key)
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)


class PhoenixPromptManagerProvider(PromptManager):
    """Phoenix implementation of PromptManager port."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,  # configurable timeout
    ) -> None:
        base_url = base_url or os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
        api_key = api_key or os.getenv("PHOENIX_API_KEY")
        self._timeout = timeout
        self._content_cache = _AsyncTTLCache(maxsize=10, ttl=300)
        try:
            self._client = Client(
                base_url=base_url,
                api_key=api_key,
                http_client=httpx.Client(
                    base_url=base_url,
                    headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                    timeout=httpx.Timeout(connect=10.0, read=timeout, write=timeout, pool=10.0),
                ),
            )
            logger.info(LogMessage.PHOENIX_PROMPT_PROVIDER_INITIALIZED, base_url, timeout)
        except Exception:
            logger.exception(LogMessage.PHOENIX_CLIENT_INIT_FAILED)
            self._client = None

    @_phoenix_retry
    async def get_prompt(
        self,
        identifier: str,
        version_id: str | None = None,
        tag: str | None = None,
    ) -> Prompt:
        if not self._client:
            raise PromptManagerUnavailableError(ErrorMessage.PROMPT_MANAGER_NOT_INITIALIZED)
        try:
            prompt_obj: PhoenixPromptVersion = self._client.prompts.get(
                prompt_identifier=identifier,
                prompt_version_id=version_id,
                tag=tag,
            )
            if not prompt_obj:
                raise PromptNotFoundError(ErrorMessage.PROMPT_NOT_FOUND.format(identifier=identifier))

            tags = self._client.prompts.tags.list(prompt_version_id=prompt_obj.id) if prompt_obj and prompt_obj.id else []
            tag_names = [t["name"] for t in tags]
            logger.info(LogMessage.PROMPT_RETRIEVED, identifier, version_id, tag_names)

            messages = _extract_messages(prompt_obj)
            return Prompt(
                identifier=identifier,
                description=getattr(prompt_obj, "_description", None),
                current_version=PromptVersion(
                    version_id=prompt_obj.id or "v1",
                    content=messages,
                    model_name=getattr(prompt_obj, "_model_name", ""),
                    tags=tag_names,
                ),
                created_at=None,
                updated_at=None,
            )
        except _PROPAGATED_ERRORS:
            raise
        except Exception as e:
            logger.exception(LogMessage.PROMPT_GET_ERROR, identifier)
            raise _wrap_phoenix_error("get_prompt", identifier, e) from e

    @_phoenix_retry
    async def get_prompt_content(
        self,
        identifier: str,
        version_id: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any]:
        cache_key = (identifier, version_id, tag)
        cached = await self._content_cache.get(cache_key)
        if cached is not None:
            return cached

        if not self._client:
            raise PromptManagerUnavailableError(ErrorMessage.PROMPT_MANAGER_NOT_INITIALIZED)
        try:
            prompt_obj = self._client.prompts.get(
                prompt_identifier=identifier,
                prompt_version_id=version_id,
                tag=tag,
            )

            tags = self._client.prompts.tags.list(prompt_version_id=prompt_obj.id) if prompt_obj and prompt_obj.id else []
            logger.info(LogMessage.PROMPT_RETRIEVED, identifier, version_id, [t["name"] for t in tags])

            messages = _extract_messages(prompt_obj)
            content = messages[0] if messages else {}
            await self._content_cache.set(cache_key, content)
            return content
        except _PROPAGATED_ERRORS:
            raise
        except Exception as e:
            logger.exception(LogMessage.PROMPT_GET_CONTENT_ERROR, identifier)
            raise _wrap_phoenix_error("get_prompt_content", identifier, e) from e

    @_phoenix_retry
    async def create_prompt(
        self,
        identifier: str,
        content: list[dict[str, str]],
        model_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> PromptVersion:
        if not self._client:
            raise PromptManagerUnavailableError(ErrorMessage.PROMPT_MANAGER_NOT_INITIALIZED)
        try:
            prompt_obj = self._client.prompts.create(
                name=identifier,
                version=PhoenixPromptVersion(content, model_name=model_name),
                prompt_description=description,
                prompt_metadata=metadata,
            )
            if tags and prompt_obj.id:
                for tag in tags:
                    try:
                        self._client.prompts.tags.create(
                            prompt_version_id=prompt_obj.id,
                            name=tag,
                        )
                    except Exception as tag_error:
                        logger.warning(LogMessage.PROMPT_TAG_ADD_FAILED, tag, identifier, tag_error)

            logger.info(LogMessage.PROMPT_VERSION_CREATED, identifier)
            return PromptVersion(
                version_id=prompt_obj.id,
                content=content,
                model_name=model_name,
                tags=tags or [],
                created_at=None,
            )
        except _PROPAGATED_ERRORS:
            raise
        except Exception as e:
            logger.exception(LogMessage.PROMPT_CREATE_ERROR, identifier)
            raise _wrap_phoenix_error("create_prompt", identifier, e) from e

    @_phoenix_retry
    async def update_prompt(
        self,
        identifier: str,
        content: list[dict[str, str]] | None = None,
        model_name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> PromptVersion:
        if not self._client:
            raise PromptManagerUnavailableError(ErrorMessage.PROMPT_MANAGER_NOT_INITIALIZED)
        if description is not None:
            logger.warning(
                LogMessage.PHOENIX_DESC_UPDATE_UNSUPPORTED,
                identifier
            )
        try:
            current = await self.get_prompt(identifier)
            updated = self._client.prompts.create(
                name=identifier,
                version=PhoenixPromptVersion(content, model_name=model_name),
                prompt_description=description or current.description,
                prompt_metadata=metadata,
            )
            logger.info(LogMessage.PROMPT_VERSION_UPDATED, identifier)
            return PromptVersion(
                version_id=updated.id,
                content=content or [],
                model_name=model_name or "",
                tags=[],
                created_at=None,
            )
        except _PROPAGATED_ERRORS:
            raise
        except Exception as e:
            logger.exception(LogMessage.PROMPT_UPDATE_ERROR, identifier)
            raise _wrap_phoenix_error("update_prompt", identifier, e) from e

    async def add_tag(self, identifier: str, tag: str) -> None:
        if not self._client:
            raise PromptManagerUnavailableError(ErrorMessage.PROMPT_MANAGER_NOT_INITIALIZED)
        try:
            self._client.prompts.tags.create(
                prompt_version_id=identifier,
                name=tag,
            )
            logger.info(LogMessage.PROMPT_TAG_ADDED, tag, identifier)
        except _PROPAGATED_ERRORS:
            raise
        except Exception as e:
            logger.exception(LogMessage.PROMPT_TAG_ADD_ERROR, tag, identifier)
            raise _wrap_phoenix_error("add_tag", identifier, e) from e
