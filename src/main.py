"""Main entry point for the Composable Agents API."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.application.routes.agents import router as agents_router
from src.application.routes.chat import router as chat_router
from src.application.routes.health import router as health_router
from src.application.routes.prompt import router as prompt_router
from src.application.routes.store import router as store_router
from src.application.routes.threads import router as threads_router
from src.application.routes.trace import router as trace_router
from src.application.routes.websocket import router as websocket_router
from src.config import Settings
from src.dependencies import (
    close_persistence,
    init_persistence,
    mcp_tool_loader,
    security,
    tracing_provider,
)
from src.domain.errors.agent import AgentConfigAlreadyExistsError, AgentError, AgentNotFoundError
from src.domain.errors.base import DomainError
from src.domain.errors.config import ConfigError, ConfigNotFoundError, ConfigValidationError
from src.domain.errors.hitl import InvalidHitlActionError
from src.domain.errors.mcp import McpError
from src.domain.errors.prompt import (
    PromptAlreadyExistsError,
    PromptManagerUnavailableError,
    PromptNotFoundError,
)
from src.domain.errors.security import InvalidApiKeyError
from src.domain.errors.storage import StorageError
from src.domain.errors.store_file import StoreFileNotFoundError
from src.domain.errors.thread import ThreadNotFoundError
from src.domain.logging.messages import LogMessage
from src.infrastructure.logging import RequestIdMiddleware, configure_logging

settings = Settings()

configure_logging(settings)

logger = logging.getLogger(__name__)


def _run_alembic_upgrade() -> None:
    from alembic.config import Config

    from alembic import command

    alembic_dir = Path(__file__).parent
    cfg = Config(str(alembic_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(alembic_dir / "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(LogMessage.APP_STARTUP_INITIATED)
    try:
        await init_persistence()
        logger.info(LogMessage.APP_PERSISTENCE_INITIALIZED)
    except Exception:
        logger.exception(LogMessage.APP_PERSISTENCE_INIT_FAILED)
    logger.info(LogMessage.APP_STARTUP_COMPLETE)
    yield
    logger.info(LogMessage.APP_SHUTDOWN_INITIATED)
    try:
        await close_persistence()
        logger.info(LogMessage.APP_PERSISTENCE_CLOSED)
    except Exception:
        logger.exception(LogMessage.APP_PERSISTENCE_CLOSE_FAILED)
    try:
        await mcp_tool_loader.close()
        logger.info(LogMessage.APP_MCP_LOADER_CLOSED)
    except Exception:
        logger.exception(LogMessage.APP_MCP_LOADER_CLOSE_FAILED)
    try:
        await tracing_provider.flush()
        await tracing_provider.shutdown()
        logger.info(LogMessage.APP_TRACING_SHUTDOWN)
    except Exception:
        logger.exception(LogMessage.APP_TRACING_SHUTDOWN_FAILED)
    logger.info(LogMessage.APP_SHUTDOWN_COMPLETE)


app = FastAPI(
    title="composable-agents",
    description="Compose an agent using Deep Agent LangGraph and expose it via FastAPI.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)

# WebSocket routes manage their own API key validation via verify_api_key_ws
# because FastAPI APIRouter(dependencies=...) does not apply to WebSocket endpoints.
app.include_router(websocket_router)

# All non-WebSocket routes except health are protected behind the API key check.
protected = APIRouter(dependencies=[Depends(security.verify_api_key)])
protected.include_router(threads_router)
protected.include_router(chat_router)
protected.include_router(trace_router)
protected.include_router(agents_router)
protected.include_router(prompt_router)
protected.include_router(store_router)
app.include_router(protected)


def _error_response(exc: DomainError) -> JSONResponse:
    """Build a JSON response from any domain error.

    Each domain error carries its own ``status_code`` (an :class:`ErrorCode`)
    and ``detail`` text, so the response shape is uniform for every type.
    :class:`ConfigValidationError` additionally exposes structured ``errors``.
    """
    content: dict = {"detail": exc.detail}
    if isinstance(exc, ConfigValidationError):
        content["errors"] = exc.errors
    return JSONResponse(status_code=int(exc.status_code), content=content)


async def agent_config_already_exists_handler(_request: Request, exc: AgentConfigAlreadyExistsError) -> JSONResponse:
    logger.warning(LogMessage.LOG_AGENT_CONFIG_ALREADY_EXISTS, exc.detail)
    return _error_response(exc)


async def storage_error_handler(_request: Request, exc: StorageError) -> JSONResponse:
    logger.error(LogMessage.LOG_STORAGE_ERROR, exc.detail)
    return _error_response(exc)


async def agent_not_found_handler(_request: Request, exc: AgentNotFoundError) -> JSONResponse:
    logger.warning(LogMessage.LOG_AGENT_NOT_FOUND, exc.detail)
    return _error_response(exc)


async def config_not_found_handler(_request: Request, exc: ConfigNotFoundError) -> JSONResponse:
    logger.warning(LogMessage.LOG_CONFIG_NOT_FOUND, exc.detail)
    return _error_response(exc)


async def thread_not_found_handler(_request: Request, exc: ThreadNotFoundError) -> JSONResponse:
    logger.warning(LogMessage.LOG_THREAD_NOT_FOUND, exc.detail)
    return _error_response(exc)


async def store_file_not_found_handler(_request: Request, exc: StoreFileNotFoundError) -> JSONResponse:
    logger.warning("Store file not found: %s", exc.detail)
    return _error_response(exc)


async def prompt_not_found_handler(_request: Request, exc: PromptNotFoundError) -> JSONResponse:
    logger.warning(LogMessage.LOG_PROMPT_NOT_FOUND, exc.detail)
    return _error_response(exc)


async def prompt_already_exists_handler(_request: Request, exc: PromptAlreadyExistsError) -> JSONResponse:
    logger.warning(LogMessage.LOG_PROMPT_ALREADY_EXISTS, exc.detail)
    return _error_response(exc)


async def prompt_manager_unavailable_handler(_request: Request, exc: PromptManagerUnavailableError) -> JSONResponse:
    logger.error(LogMessage.LOG_PROMPT_MANAGER_UNAVAILABLE, exc.detail)
    return _error_response(exc)


async def invalid_hitl_action_handler(_request: Request, exc: InvalidHitlActionError) -> JSONResponse:
    logger.warning(LogMessage.LOG_INVALID_HITL_ACTION, exc.detail)
    return _error_response(exc)


async def config_validation_handler(_request: Request, exc: ConfigValidationError) -> JSONResponse:
    logger.error(LogMessage.LOG_CONFIG_VALIDATION_ERROR, exc.detail, exc.errors)
    return _error_response(exc)


async def config_error_handler(_request: Request, exc: ConfigError) -> JSONResponse:
    logger.error(LogMessage.LOG_CONFIG_ERROR, exc.detail)
    return _error_response(exc)


async def agent_error_handler(_request: Request, exc: AgentError) -> JSONResponse:
    logger.error(LogMessage.LOG_AGENT_ERROR, exc.detail)
    return _error_response(exc)


async def mcp_error_handler(_request: Request, exc: McpError) -> JSONResponse:
    logger.error(LogMessage.LOG_MCP_ERROR, exc.detail)
    return _error_response(exc)


async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    logger.error(LogMessage.LOG_UNHANDLED_DOMAIN_ERROR, exc.detail)
    return _error_response(exc)


async def invalid_api_key_handler(_request: Request, exc: InvalidApiKeyError) -> JSONResponse:
    logger.warning(LogMessage.LOG_INVALID_API_KEY, exc.detail)
    return _error_response(exc)


# Register one handler per domain error type explicitly. Each handler reads the
# exception's own status_code/detail, so no separate error->HTTP mapping table
# is required. Most-specific types are registered first.
app.add_exception_handler(ConfigNotFoundError, config_not_found_handler)
app.add_exception_handler(ConfigValidationError, config_validation_handler)
app.add_exception_handler(ConfigError, config_error_handler)
app.add_exception_handler(ThreadNotFoundError, thread_not_found_handler)
app.add_exception_handler(StoreFileNotFoundError, store_file_not_found_handler)
app.add_exception_handler(AgentNotFoundError, agent_not_found_handler)
app.add_exception_handler(AgentConfigAlreadyExistsError, agent_config_already_exists_handler)
app.add_exception_handler(AgentError, agent_error_handler)
app.add_exception_handler(InvalidHitlActionError, invalid_hitl_action_handler)
app.add_exception_handler(StorageError, storage_error_handler)
app.add_exception_handler(McpError, mcp_error_handler)
app.add_exception_handler(PromptNotFoundError, prompt_not_found_handler)
app.add_exception_handler(PromptAlreadyExistsError, prompt_already_exists_handler)
app.add_exception_handler(PromptManagerUnavailableError, prompt_manager_unavailable_handler)
app.add_exception_handler(InvalidApiKeyError, invalid_api_key_handler)
app.add_exception_handler(DomainError, domain_error_handler)


def run_fastapi():
    logger.info(LogMessage.APP_MIGRATIONS_RUNNING)
    _run_alembic_upgrade()
    logger.info(LogMessage.APP_MIGRATIONS_DONE)

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    run_fastapi()
