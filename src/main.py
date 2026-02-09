from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.application.routes.agents import router as agents_router
from src.application.routes.chat import router as chat_router
from src.application.routes.health import router as health_router
from src.application.routes.threads import router as threads_router
from src.application.routes.websocket import router as websocket_router
from src.config import Settings
from src.dependencies import close_dependencies, init_dependencies
from src.domain.exceptions import (
    AgentError,
    AgentNotFoundError,
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    DomainError,
    ThreadNotFoundError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize dependencies on startup, cleanup on shutdown."""
    settings = Settings()
    await init_dependencies(settings)
    yield
    await close_dependencies()


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
async def agent_not_found_handler(request: Request, exc: AgentNotFoundError) -> JSONResponse:
    """Handle unknown agent names with a 404 response."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConfigNotFoundError)
async def config_not_found_handler(request: Request, exc: ConfigNotFoundError) -> JSONResponse:
    """Handle missing configuration files with a 404 response."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ThreadNotFoundError)
async def thread_not_found_handler(request: Request, exc: ThreadNotFoundError) -> JSONResponse:
    """Handle missing threads with a 404 response."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConfigValidationError)
async def config_validation_handler(request: Request, exc: ConfigValidationError) -> JSONResponse:
    """Handle configuration validation errors with a 422 response."""
    return JSONResponse(status_code=422, content={"detail": str(exc), "errors": exc.errors})


@app.exception_handler(ConfigError)
async def config_error_handler(request: Request, exc: ConfigError) -> JSONResponse:
    """Handle general configuration errors with a 400 response."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(AgentError)
async def agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
    """Handle agent execution errors with a 502 response."""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Handle generic domain errors with a 500 response."""
    return JSONResponse(status_code=500, content={"detail": str(exc)})
