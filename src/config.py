from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class TracingSettings(BaseSettings):
    provider: str = "none"
    enabled: bool = False
    endpoint: str | None = None
    project_name: str = "composable-agents"
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    phoenix_collector_endpoint: str | None = None
    phoenix_api_key: str | None = None
    langchain_api_key: str | None = None
    langchain_project: str | None = None


class Settings(BaseSettings):
    agents_dir: str = "./agents"
    openai_api_key: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    tracing: TracingSettings = TracingSettings()

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
