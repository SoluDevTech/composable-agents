"""End-to-end tests for the ``/api/v1/api-keys`` router.

Builds a minimal FastAPI app with the ``api_keys`` router and overrides the
``get_current_user_id`` dependency to return a fixed user id. Uses
``httpx.ASGITransport`` + ``AsyncClient`` so no HTTP server is started.

The router (``src.application.routes.api_keys``), the
``get_current_user_id`` dependency (``src.dependencies``), the request DTO
(``src.application.requests.api_key``) and the exception types do not exist
yet, so these tests fail at import until the green-phase implementation.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.application.routes.api_keys import router as api_keys_router
from src.dependencies import (
    get_create_api_key_use_case,
    get_current_user_id,
    get_list_api_keys_use_case,
    get_revoke_api_key_use_case,
)
from src.domain.errors.security import ApiKeyError, ApiKeyNotFoundError, AuthenticationError
from src.infrastructure.postgres_api_key.adapter import PostgresApiKeyRepository

_USER_ID = "user-test-123"


def _build_app(repo: PostgresApiKeyRepository, *, user_id: str | None = _USER_ID) -> FastAPI:
    """Build a minimal FastAPI app with the api_keys router wired to a real repo.

    When ``user_id`` is ``None``, the ``get_current_user_id`` override raises
    ``AuthenticationError`` so the 401 path can be exercised.
    """
    app = FastAPI()
    app.include_router(api_keys_router)

    if user_id is None:

        def _raise() -> str:
            raise AuthenticationError("Invalid or missing credentials")

        app.dependency_overrides[get_current_user_id] = _raise
    else:
        app.dependency_overrides[get_current_user_id] = lambda: user_id

    app.dependency_overrides[get_create_api_key_use_case] = lambda: _make_create(repo)
    app.dependency_overrides[get_list_api_keys_use_case] = lambda: _make_list(repo)
    app.dependency_overrides[get_revoke_api_key_use_case] = lambda: _make_revoke(repo)

    _register_handlers(app)
    return app


def _make_create(repo):
    from src.application.use_cases.api_key.create_api_key import CreateApiKeyUseCase

    return CreateApiKeyUseCase(repo=repo)


def _make_list(repo):
    from src.application.use_cases.api_key.list_api_keys import ListApiKeysUseCase

    return ListApiKeysUseCase(repo=repo)


def _make_revoke(repo):
    from src.application.use_cases.api_key.revoke_api_key import RevokeApiKeyUseCase

    return RevokeApiKeyUseCase(repo=repo)


def _register_handlers(app: FastAPI) -> None:
    """Register exception handlers matching the production handler shape."""

    async def _auth_err(_req, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})

    async def _api_key_err(_req, exc: ApiKeyError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})

    async def _not_found_err(_req, exc: ApiKeyNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})

    app.add_exception_handler(AuthenticationError, _auth_err)
    app.add_exception_handler(ApiKeyError, _api_key_err)
    app.add_exception_handler(ApiKeyNotFoundError, _not_found_err)


@pytest.fixture
async def repo(db_engine) -> PostgresApiKeyRepository:
    return PostgresApiKeyRepository(engine=db_engine)


@pytest.fixture
def app(repo) -> FastAPI:
    return _build_app(repo, user_id=_USER_ID)


@pytest.fixture
def auth_failure_app(repo) -> FastAPI:
    return _build_app(repo, user_id=None)


class TestCreateApiKeyRoute:
    """``POST /api/v1/api-keys``."""

    async def test_post_returns_201_with_plaintext_and_persists(self, app, repo, db_engine):
        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/api-keys", json={"name": "my key"})

        # Assert — response shape
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "my key"
        assert body["plaintext"].startswith("cpk_")
        assert body["key_prefix"] == body["plaintext"][:10]
        assert body["id"]
        assert body["created_at"]

        # Assert — row persisted in DB
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        from src.infrastructure.database.models.api_key import ApiKeyModel

        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            row = await session.execute(select(ApiKeyModel).where(ApiKeyModel.id == body["id"]))
        assert row.scalar_one() is not None

    async def test_post_empty_name_returns_422(self, app):
        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/api-keys", json={"name": ""})

        # Assert — pydantic min_length=1 yields 422 from FastAPI validation
        assert resp.status_code == 422

    async def test_post_missing_name_field_returns_422(self, app):
        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/api-keys", json={})

        # Assert
        assert resp.status_code == 422

    async def test_post_unauthenticated_returns_401(self, auth_failure_app):
        # Act
        transport = ASGITransport(app=auth_failure_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/api-keys", json={"name": "x"})

        # Assert
        assert resp.status_code == 401


class TestListApiKeysRoute:
    """``GET /api/v1/api-keys``."""

    async def test_get_returns_200_list_after_create(self, app):
        # Arrange — create one key first
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v1/api-keys", json={"name": "first"})

            # Act
            resp = await client.get("/api/v1/api-keys")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["name"] == "first"
        assert "key_hash" not in body[0]

    async def test_get_unauthenticated_returns_401(self, auth_failure_app):
        # Act
        transport = ASGITransport(app=auth_failure_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/api-keys")

        # Assert
        assert resp.status_code == 401


class TestRevokeApiKeyRoute:
    """``DELETE /api/v1/api-keys/{key_id}``."""

    async def test_delete_returns_204(self, app):
        # Arrange — create a key
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/v1/api-keys", json={"name": "to-revoke"})
            key_id = created.json()["id"]

            # Act
            resp = await client.delete(f"/api/v1/api-keys/{key_id}")

        # Assert
        assert resp.status_code == 204

    async def test_delete_already_revoked_returns_204_idempotent(self, app):
        # Arrange
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/v1/api-keys", json={"name": "k"})
            key_id = created.json()["id"]

            # Act — delete twice
            first = await client.delete(f"/api/v1/api-keys/{key_id}")
            second = await client.delete(f"/api/v1/api-keys/{key_id}")

        # Assert — both succeed (idempotent revoke)
        assert first.status_code == 204
        assert second.status_code == 204

    async def test_delete_never_existed_returns_404(self, app):
        # Arrange
        from uuid import uuid4

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            resp = await client.delete(f"/api/v1/api-keys/{uuid4().hex}")

        # Assert
        assert resp.status_code == 404

    async def test_delete_unauthenticated_returns_401(self, auth_failure_app):
        # Act
        from uuid import uuid4

        transport = ASGITransport(app=auth_failure_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/api/v1/api-keys/{uuid4().hex}")

        # Assert
        assert resp.status_code == 401
