import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.application.routes.agents import router as agents_router
from src.application.routes.chat import router as chat_router
from src.application.routes.health import router as health_router
from src.application.routes.threads import router as threads_router
from src.application.routes.websocket import router as websocket_router
from src.dependencies import agent_registry, mcp_tool_loader, tracing_provider
from src.domain.exceptions import (
    AgentError,
    AgentNotFoundError,
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    DomainError,
    ThreadNotFoundError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("composable-agents")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan: cleanup on shutdown."""
    logger.info("Application startup complete")
    yield
    logger.info("Application shutdown initiated")
    try:
        await agent_registry.close()
        logger.info("Agent registry closed")
    except Exception:
        logger.exception("Error closing agent registry")
    try:
        await mcp_tool_loader.close()
        logger.info("MCP tool loader closed")
    except Exception:
        logger.exception("Error closing MCP tool loader")
    try:
        await tracing_provider.flush()
        await tracing_provider.shutdown()
        logger.info("Tracing provider shut down")
    except Exception:
        logger.exception("Error shutting down tracing provider")
    logger.info("Application shutdown complete")


app = FastAPI(
    title="composable-agents",
    description="Compose an agent using Deep Agent LangGraph and expose it via FastAPI.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(threads_router)
app.include_router(chat_router)
app.include_router(agents_router)
app.include_router(websocket_router)


@app.exception_handler(AgentNotFoundError)
async def agent_not_found_handler(_request: Request, exc: AgentNotFoundError) -> JSONResponse:
    logger.warning("Agent not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConfigNotFoundError)
async def config_not_found_handler(_request: Request, exc: ConfigNotFoundError) -> JSONResponse:
    logger.warning("Config not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ThreadNotFoundError)
async def thread_not_found_handler(_request: Request, exc: ThreadNotFoundError) -> JSONResponse:
    logger.warning("Thread not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConfigValidationError)
async def config_validation_handler(_request: Request, exc: ConfigValidationError) -> JSONResponse:
    logger.error("Config validation error: %s errors=%s", exc, exc.errors)
    return JSONResponse(status_code=422, content={"detail": str(exc), "errors": exc.errors})


@app.exception_handler(ConfigError)
async def config_error_handler(_request: Request, exc: ConfigError) -> JSONResponse:
    logger.error("Config error: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(AgentError)
async def agent_error_handler(_request: Request, exc: AgentError) -> JSONResponse:
    logger.error("Agent error: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    logger.error("Domain error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})
