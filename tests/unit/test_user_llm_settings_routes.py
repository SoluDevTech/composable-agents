"""End-to-end tests for the ``/api/v1/settings/llm`` router.

Builds a minimal FastAPI app with the ``user_llm_settings`` router and overrides
the ``get_current_user_id`` dependency to return a fixed user id. Uses real
internal components (real repo + real FernetCrypto via the ``db_engine``
fixture) — no mocks on internal components.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.application.routes.user_llm_settings import router as llm_settings_router
from src.application.use_cases.user_llm_settings.delete_user_llm_settings import DeleteUserLlmSettingsUseCase
from src.application.use_cases.user_llm_settings.get_user_llm_settings import GetUserLlmSettingsUseCase
from src.application.use_cases.user_llm_settings.upsert_user_llm_settings import (
    UpsertUserLlmSettingsUseCase,
)
from src.dependencies import (
    get_current_user_id,
    get_delete_user_llm_settings_use_case,
    get_get_user_llm_settings_use_case,
    get_upsert_user_llm_settings_use_case,
)
from src.domain.errors.security import AuthenticationError
from src.infrastructure.crypto.fernet_crypto import FernetCrypto
from src.infrastructure.postgres_user_llm.adapter import PostgresUserLlmSettingsRepository

_USER_ID = "user-test-123"
_TEST_KEY = "Yr5R5-6lRUaxEwZWVysIaFs5POHcLps2OZViwWAscaU="


def _build_app(
    repo: PostgresUserLlmSettingsRepository, crypto: FernetCrypto, *, user_id: str | None = _USER_ID
) -> FastAPI:
    """Build a minimal FastAPI app with the LLM settings router wired to real adapters."""
    app = FastAPI()
    app.include_router(llm_settings_router)

    if user_id is None:

        def _raise() -> str:
            raise AuthenticationError("Invalid or missing credentials")

        app.dependency_overrides[get_current_user_id] = _raise
    else:
        app.dependency_overrides[get_current_user_id] = lambda: user_id

    app.dependency_overrides[get_get_user_llm_settings_use_case] = lambda: GetUserLlmSettingsUseCase(repo=repo)
    app.dependency_overrides[get_upsert_user_llm_settings_use_case] = lambda: UpsertUserLlmSettingsUseCase(
        repo=repo, crypto=crypto
    )
    app.dependency_overrides[get_delete_user_llm_settings_use_case] = lambda: DeleteUserLlmSettingsUseCase(repo=repo)

    _register_handlers(app)
    return app


def _register_handlers(app: FastAPI) -> None:
    async def _auth_err(_req, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})

    app.add_exception_handler(AuthenticationError, _auth_err)


@pytest.fixture
def crypto() -> FernetCrypto:
    return FernetCrypto(key=_TEST_KEY)


@pytest.fixture
async def repo(db_engine, crypto) -> PostgresUserLlmSettingsRepository:
    return PostgresUserLlmSettingsRepository(engine=db_engine, crypto=crypto)


@pytest.fixture
def app(repo, crypto) -> FastAPI:
    return _build_app(repo, crypto, user_id=_USER_ID)


@pytest.fixture
def auth_failure_app(repo, crypto) -> FastAPI:
    return _build_app(repo, crypto, user_id=None)


class TestGetLlmSettings:
    async def test_get_returns_200_none_when_absent(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/settings/llm")
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_get_unauthenticated_returns_401(self, auth_failure_app):
        transport = ASGITransport(app=auth_failure_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/settings/llm")
        assert resp.status_code == 401


class TestPutLlmSettings:
    async def test_put_returns_200_and_masks_api_key(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/settings/llm",
                json={"provider": "openai", "base_url": "https://api.openai.com/v1", "api_key": "sk-secret-12345"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "openai"
        assert body["base_url"] == "https://api.openai.com/v1"
        assert body["api_key_masked"] is not None
        assert "sk-secret-12345" not in body["api_key_masked"]
        assert "..." in body["api_key_masked"]

    async def test_put_then_get_returns_masked(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.put(
                "/api/v1/settings/llm",
                json={"provider": "openrouter", "base_url": "https://openrouter.ai/v1", "api_key": "sk-abc"},
            )
            resp = await client.get("/api/v1/settings/llm")
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "openrouter"
        assert body["api_key_masked"] != "sk-abc"

    async def test_put_empty_fields_returns_422(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/api/v1/settings/llm", json={"provider": "", "base_url": "", "api_key": ""})
        assert resp.status_code == 422

    async def test_put_missing_field_returns_422(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put("/api/v1/settings/llm", json={"provider": "openai"})
        assert resp.status_code == 422

    async def test_put_unauthenticated_returns_401(self, auth_failure_app):
        transport = ASGITransport(app=auth_failure_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/settings/llm",
                json={"provider": "openai", "base_url": "x", "api_key": "y"},
            )
        assert resp.status_code == 401


class TestDeleteLlmSettings:
    async def test_delete_returns_204(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.put(
                "/api/v1/settings/llm",
                json={"provider": "openai", "base_url": "https://api.openai.com/v1", "api_key": "sk-test"},
            )
            resp = await client.delete("/api/v1/settings/llm")
        assert resp.status_code == 204

    async def test_delete_then_get_returns_none(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.put(
                "/api/v1/settings/llm",
                json={"provider": "openai", "base_url": "x", "api_key": "sk-test"},
            )
            await client.delete("/api/v1/settings/llm")
            resp = await client.get("/api/v1/settings/llm")
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_delete_absent_returns_204(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/api/v1/settings/llm")
        assert resp.status_code == 204

    async def test_delete_unauthenticated_returns_401(self, auth_failure_app):
        transport = ASGITransport(app=auth_failure_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/api/v1/settings/llm")
        assert resp.status_code == 401
