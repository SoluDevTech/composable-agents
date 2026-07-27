"""End-to-end tests for ``verify_credentials`` wiring on the real FastAPI app.

The real ``src.main.app`` switches its ``protected`` APIRouter from
``security.verify_api_key`` (master key) to ``security.verify_credentials``
(dual JWT / API-key). These tests build the real app and override:

* ``security.verify_credentials`` is NOT overridden — we exercise the real
  dependency by injecting a mocked :class:`AuthService` via
  ``security.set_auth_service``.
* The use cases are overridden to wired real repositories backed by the
  ``db_engine`` fixture (so listing threads does not require an agent runner).
* The ``AuthenticationError`` handler is the one registered in ``src.main``.

Scenarios:

* ``GET /api/v1/threads`` with valid ``Authorization: Bearer …`` → 200.
* ``GET /api/v1/threads`` with no credentials → 401.
* ``GET /api/v1/threads`` with valid ``X-API-Key: cpk_…`` → 200.
* ``GET /api/v1/threads`` with wrong API key → 401.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.dependencies import (
    get_create_thread_use_case,
    get_list_threads_use_case,
    security,
)
from src.domain.entities.user.user import User
from src.domain.ports.auth.api_key_repository import ApiKeyRepository
from src.domain.ports.auth.jwt_service import JwtServicePort
from src.domain.services.auth.auth_service import AuthService


@pytest.fixture
def jwt_port() -> AsyncMock:
    mock = AsyncMock(spec=JwtServicePort)
    mock.decode_token.return_value = User(sub="u1", email="a@b.c")
    return mock


@pytest.fixture
def api_key_repo() -> AsyncMock:
    mock = AsyncMock(spec=ApiKeyRepository)
    mock.find_active_by_hash.return_value = ("u1", "k1")
    return mock


@pytest.fixture(autouse=True)
def _wire_auth_service(jwt_port, api_key_repo):
    """Inject a real AuthService with mocked ports into the singleton security."""
    auth_service = AuthService(jwt_port=jwt_port, api_key_repo=api_key_repo)
    security.set_auth_service(auth_service)
    yield
    # Reset to None so other tests see the unwired state.
    security._auth_service = None  # noqa: SLF001


@pytest_asyncio.fixture
async def app_with_overrides(db_engine) -> AsyncGenerator:
    """Build the real app with use cases overridden to use the SQLite engine."""
    from src.application.use_cases.create_thread import CreateThreadUseCase
    from src.application.use_cases.list_threads import ListThreadsUseCase

    # We need a stub registry that allows any agent name for create_thread.
    from src.domain.ports.agent_registry import AgentRegistry
    from src.domain.ports.agent_runner import AgentRunner
    from src.infrastructure.postgres_thread.adapter import PostgresThreadRepository

    class _StubRegistry(AgentRegistry):
        async def get_runner(self, agent_name: str) -> AgentRunner:
            raise RuntimeError("not used")

        async def list_agents(self) -> list[str]:
            return ["agent-x"]

        async def invalidate(self, agent_name: str) -> None:
            pass

        async def close(self) -> None:
            pass

    thread_repo = PostgresThreadRepository(engine=db_engine)

    from src.main import app

    app.dependency_overrides[get_create_thread_use_case] = lambda: CreateThreadUseCase(thread_repo, _StubRegistry())
    app.dependency_overrides[get_list_threads_use_case] = lambda: ListThreadsUseCase(thread_repo)
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app_with_overrides) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app_with_overrides)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestVerifyCredentialsWiring:
    """The ``protected`` router uses ``verify_credentials`` (dual auth)."""

    async def test_valid_jwt_returns_200(self, client, jwt_port):
        # Act
        resp = await client.get("/api/v1/threads", headers={"Authorization": "Bearer valid"})

        # Assert
        assert resp.status_code == 200
        assert resp.json() == []
        # The JWT port was actually called
        jwt_port.decode_token.assert_awaited()

    async def test_no_credentials_returns_401(self, client):
        # Act
        resp = await client.get("/api/v1/threads")

        # Assert
        assert resp.status_code == 401

    async def test_valid_api_key_returns_200(self, client, api_key_repo):
        # Act
        resp = await client.get("/api/v1/threads", headers={"X-API-Key": "cpk_valid"})

        # Assert
        assert resp.status_code == 200
        api_key_repo.find_active_by_hash.assert_awaited()

    async def test_wrong_api_key_returns_401(self, client, api_key_repo):
        # Arrange
        api_key_repo.find_active_by_hash.return_value = None
        # Act
        resp = await client.get("/api/v1/threads", headers={"X-API-Key": "cpk_wrong"})
        # Assert
        assert resp.status_code == 401

    async def test_invalid_jwt_returns_401(self, client, jwt_port):
        # Arrange
        jwt_port.decode_token.return_value = None
        # Act
        resp = await client.get("/api/v1/threads", headers={"Authorization": "Bearer bogus"})
        # Assert
        assert resp.status_code == 401

    async def test_authenticated_request_sets_user_id_contextvar(self, client, jwt_port):
        """The wiring sets current_user_id so the thread is created under u1."""
        # Arrange + Act — create a thread then list
        create_resp = await client.post(
            "/api/v1/threads",
            json={"agent_name": "agent-x"},
            headers={"Authorization": "Bearer valid"},
        )
        assert create_resp.status_code == 201
        list_resp = await client.get("/api/v1/threads", headers={"Authorization": "Bearer valid"})
        assert list_resp.status_code == 200
        # The created thread is visible to u1
        assert len(list_resp.json()) == 1
