"""End-to-end tests for the ``/api/v1/users/me`` router.

Builds a minimal FastAPI app with the ``users`` router and overrides the
``get_current_auth_context`` dependency to return a fixed :class:`AuthContext`
(no real JWT / oauth2-proxy needed). Uses ``httpx.ASGITransport`` +
``AsyncClient`` so no HTTP server is started.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.application.routes.users import router as users_router
from src.application.use_cases.user.get_current_user import GetCurrentUserUseCase
from src.dependencies import (
    get_current_auth_context,
    get_get_current_user_use_case,
)
from src.domain.entities.auth.auth_context import AuthContext
from src.domain.errors.security import AuthenticationError


def _build_app(ctx: AuthContext | None) -> FastAPI:
    """Build a minimal FastAPI app with the users router wired to a fixed context.

    When ``ctx`` is ``None``, the ``get_current_auth_context`` override raises
    ``AuthenticationError`` so the 401 path can be exercised.
    """
    app = FastAPI()
    app.include_router(users_router)

    if ctx is None:

        def _raise() -> AuthContext:
            raise AuthenticationError("Invalid or missing credentials")

        app.dependency_overrides[get_current_auth_context] = _raise
    else:
        app.dependency_overrides[get_current_auth_context] = lambda: ctx
    app.dependency_overrides[get_get_current_user_use_case] = lambda: GetCurrentUserUseCase()

    async def _auth_err(_req, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})

    app.add_exception_handler(AuthenticationError, _auth_err)
    return app


class TestGetCurrentUserRoute:
    """``GET /api/v1/users/me``."""

    async def test_get_returns_profile_with_jwt_claims(self):
        # Arrange — JWT path: email / name / username propagated
        ctx = AuthContext(
            user_id="user-123",
            method="jwt",
            raw_credential="tok",
            email="jane@example.com",
            name="Jane Doe",
            username="jane",
        )
        app = _build_app(ctx)

        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/users/me")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "user_id": "user-123",
            "email": "jane@example.com",
            "name": "Jane Doe",
            "username": "jane",
        }

    async def test_get_returns_user_id_only_for_api_key_auth(self):
        # Arrange — API-key path: no profile claims
        ctx = AuthContext(user_id="user-456", method="api_key", raw_credential="cpk_xxx")
        app = _build_app(ctx)

        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/users/me")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "user_id": "user-456",
            "email": None,
            "name": None,
            "username": None,
        }

    async def test_get_with_partial_jwt_claims_returns_available_fields(self):
        # Arrange — IdP provided only email (no name / username)
        ctx = AuthContext(
            user_id="user-789",
            method="jwt",
            raw_credential="tok",
            email="partial@example.com",
        )
        app = _build_app(ctx)

        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/users/me")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "user_id": "user-789",
            "email": "partial@example.com",
            "name": None,
            "username": None,
        }

    async def test_get_unauthenticated_returns_401(self):
        # Arrange — no auth context resolved
        app = _build_app(None)

        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/users/me")

        # Assert
        assert resp.status_code == 401
