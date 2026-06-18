from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class TracingSettings(BaseSettings):
    provider: str = "none"
    enabled: bool = False
    project_name: str = "composable-agents"
    phoenix_collector_endpoint: str | None = None
    phoenix_api_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None


class Settings(BaseSettings):
    openai_api_key: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    uvicorn_log_level: str = "info"
    allowed_origins: list[str] = ["http://localhost:8080"]
    tracing: TracingSettings = TracingSettings()
    # Agent execution timeouts (seconds). The per-tool timeout isolates a hung
    # MCP tool as a recoverable ToolMessage error (agent continues). The graph
    # idle/invoke timeouts are backstops that only fire on a total stall.
    mcp_tool_timeout: float = 60.0
    agent_stream_idle_timeout: float = 120.0
    agent_invoke_timeout: float = 120.0

    minio_endpoint: str = "localhost:9040"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "composable-agents"
    minio_secure: bool = False

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_user: str = "raganything"
    postgres_password: str = "raganything"
    postgres_database: str = "raganything"

    @property
    def database_url(self) -> str:
        """Build the async PostgreSQL connection URL for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{quote_plus(self.postgres_user)}:{quote_plus(self.postgres_password)}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )
