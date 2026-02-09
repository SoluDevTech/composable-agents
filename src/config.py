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
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    tracing: TracingSettings = TracingSettings()

