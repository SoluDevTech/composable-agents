import logging
import os
from functools import wraps
from typing import TypeVar, Callable, Any
import asyncio

import httpx
from cachetools import TTLCache, cached
from phoenix.client import Client
from phoenix.client.client import _update_headers, _WrappedClient
from phoenix.client.resources.prompts import PromptVersion as PhoenixPromptVersion
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.domain.entities.prompt import Prompt, PromptVersion
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger("composable-agents")

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


class PhoenixUnavailableError(RuntimeError):
    """Raised when Phoenix is unreachable or returns a server error."""
    pass


def _wrap_phoenix_error(operation: str, identifier: str, e: Exception) -> Exception:
    """Convert raw Phoenix/httpx exceptions to meaningful domain errors."""
    if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
        return PhoenixUnavailableError(
            f"Phoenix unavailable during '{operation}' for '{identifier}': {e}"
        )
    if isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code == 404:
            return ValueError(f"Prompt not found: {identifier}")
        if e.response.status_code >= 500:
            return PhoenixUnavailableError(
                f"Phoenix server error ({e.response.status_code}) during '{operation}' for '{identifier}'"
            )
    return e


class PhoenixPromptManagerProvider(PromptManager):
    """Phoenix implementation of PromptManager port."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,  # configurable timeout
    ):
        base_url = base_url or os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
        api_key = api_key or os.getenv("PHOENIX_API_KEY")
        self._timeout = timeout
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
            logger.info("PhoenixPromptManagerProvider initialized base_url=%s timeout=%ss", base_url, timeout)
        except Exception as e:
            logger.error("Failed to initialize Phoenix client: %s", e)
            self._client = None

    @_phoenix_retry
    async def get_prompt(
        self,
        identifier: str,
        version_id: str | None = None,
        tag: str | None = None,
    ) -> Prompt:
        if not self._client:
            raise PhoenixUnavailableError("Phoenix client not initialized")
        try:
            prompt_obj: PhoenixPromptVersion = self._client.prompts.get(
                prompt_identifier=identifier,
                prompt_version_id=version_id,
                tag=tag,
            )
            if not prompt_obj:
                raise ValueError(f"Prompt not found: {identifier}")
            return self._to_domain_prompt(prompt_obj, identifier=identifier, description=prompt_obj._description)
        except (ValueError, PhoenixUnavailableError):
            raise
        except Exception as e:
            logger.error("Error getting prompt '%s': %s", identifier, e)
            raise _wrap_phoenix_error("get_prompt", identifier, e) from e

    @cached(cache=TTLCache(maxsize=10, ttl=300))
    @_phoenix_retry
    async def get_prompt_content(
        self,
        identifier: str,
        version_id: str | None = None,
        tag: str | None = None,
    ) -> dict[str, str]:
        if not self._client:
            raise PhoenixUnavailableError("Phoenix client not initialized")
        try:
            prompt_obj = self._client.prompts.get(
                prompt_identifier=identifier,
                prompt_version_id=version_id,
                tag=tag,
            )
            domain = self._to_domain_prompt(prompt_obj, identifier=identifier)
            messages = domain.current_version.content
            return messages[0] if messages else {}
        except (ValueError, PhoenixUnavailableError):
            raise
        except Exception as e:
            logger.error("Error getting prompt content '%s': %s", identifier, e)
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
    ) -> PhoenixPromptVersion:
        if not self._client:
            raise PhoenixUnavailableError("Phoenix client not initialized")
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
                        logger.warning("Failed to add tag '%s' to '%s': %s", tag, identifier, tag_error)

            logger.info("Created prompt '%s'", identifier)
            return prompt_obj
        except (ValueError, PhoenixUnavailableError):
            raise
        except Exception as e:
            logger.error("Error creating prompt '%s': %s", identifier, e)
            raise _wrap_phoenix_error("create_prompt", identifier, e) from e

    @_phoenix_retry
    async def update_prompt(
        self,
        identifier: str,
        content: list[dict[str, str]] | None = None,
        model_name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> PhoenixPromptVersion:
        if not self._client:
            raise PhoenixUnavailableError("Phoenix client not initialized")
        if description is not None:
            logger.warning(
                "Phoenix does not support updating description on existing prompts — description change ignored for '%s'",
                identifier
            )
        try:
            current = await self.get_prompt(identifier)
            updated = self._client.prompts.create(
                name=identifier,
                version=PhoenixPromptVersion(content, model_name=model_name),
                prompt_description=description or current.description,
            )
            logger.info("Updated prompt '%s'", identifier)
            return updated
        except (ValueError, PhoenixUnavailableError):
            raise
        except Exception as e:
            logger.error("Error updating prompt '%s': %s", identifier, e)
            raise _wrap_phoenix_error("update_prompt", identifier, e) from e

    async def add_tag(self, identifier: str, tag: str) -> None:
        if not self._client:
            raise PhoenixUnavailableError("Phoenix client not initialized")
        try:
            self._client.prompts.tags.create(
                prompt_version_id=identifier,
                name=tag,
            )
            logger.info("Added tag '%s' to prompt '%s'", tag, identifier)
        except Exception as e:
            logger.error("Error adding tag '%s' to '%s': %s", tag, identifier, e)
            raise _wrap_phoenix_error("add_tag", identifier, e) from e

    def _to_domain_prompt(
        self,
        phoenix_prompt,
        identifier: str | None = None,
        description: str | None = None,
    ) -> Prompt:
        template = getattr(phoenix_prompt, "_template", {})
        raw_messages = template.get("messages", []) if isinstance(template, dict) else []

        messages = []
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

        return Prompt(
            identifier=identifier or "",
            description=description or getattr(phoenix_prompt, "_description", None),
            current_version=PromptVersion(
                version_id=phoenix_prompt.id or "v1",
                content=messages,
                model_name=getattr(phoenix_prompt, "_model_name", ""),
                tags=[],
            ),
            created_at=None,
            updated_at=None,
        )
