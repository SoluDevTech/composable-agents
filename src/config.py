from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from pydantic import PrivateAttr, model_validator
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
    api_key: str = ""
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

    database_url: str = ""
    postgres_statement_cache_size: int | None = None
    _ssl_mode: str | None = PrivateAttr(default=None)

    @property
    def ssl_mode(self) -> str | None:
        return self._ssl_mode

    @model_validator(mode="after")
    def normalize_database_url(self) -> "Settings":
        """Normalize DATABASE_URL for asyncpg.

        - postgresql:// or postgres:// → postgresql+asyncpg://
        - Extract sslmode and store it (passed via connect_args, not URL)
        - Strip sslmode and channel_binding (asyncpg doesn't accept them as query params)
        """
        if not self.database_url:
            return self

        parsed = urlsplit(self.database_url)
        params = parse_qs(parsed.query)
        ssl_values = params.get("sslmode")
        if ssl_values:
            self._ssl_mode = ssl_values[0]

        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        elif self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace(
                "postgres://", "postgresql+asyncpg://", 1
            )

        parsed = urlsplit(self.database_url)
        params = parse_qs(parsed.query)
        params.pop("sslmode", None)
        params.pop("channel_binding", None)
        new_query = urlencode(params, doseq=True)
        self.database_url = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
        )
        return self
