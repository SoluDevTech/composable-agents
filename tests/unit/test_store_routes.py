"""Tests for store file management routes (GET/PUT/DELETE /api/v1/store/files).

Mirrors the pattern from ``tests/unit/test_routes.py``: dependencies are wired
through ``app.dependency_overrides`` (FastAPI stays in control of its own
providers), the API key check is bypassed, and requests go through
``httpx.AsyncClient`` with ``ASGITransport``.

The store-file use cases are mocked at the use-case port boundary (they wrap
the repository, which itself wraps the external LangGraph ``BaseStore``). Each
use case is replaced with an ``AsyncMock`` so the route layer is exercised
against its real FastAPI wiring while the persistence layer is stubbed.

These tests are written TDD-Red: ``src.application.routes.store``,
``src.application.use_cases.manage_store_file`` and the
``get_*_store_file_use_case`` providers do not exist yet, so importing them
raises ``ImportError`` and every test fails until the implementation lands.
"""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.application.use_cases.manage_store_file import (
    DeleteStoreFileUseCase,
    GetStoreFileUseCase,
    ListStoreFilesUseCase,
    PutStoreFileUseCase,
)
from src.dependencies import (
    get_delete_store_file_use_case,
    get_get_store_file_use_case,
    get_list_store_files_use_case,
    get_put_store_file_use_case,
)
from src.domain.errors.storage import StorageError
from src.main import app, security

# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def mock_list_use_case() -> AsyncMock:
    uc = AsyncMock(spec=ListStoreFilesUseCase)
    uc.execute = AsyncMock(return_value=[])
    return uc


@pytest.fixture
def mock_get_use_case() -> AsyncMock:
    uc = AsyncMock(spec=GetStoreFileUseCase)
    uc.execute = AsyncMock(return_value=None)
    return uc


@pytest.fixture
def mock_put_use_case() -> AsyncMock:
    uc = AsyncMock(spec=PutStoreFileUseCase)
    uc.execute = AsyncMock(return_value=None)
    return uc


@pytest.fixture
def mock_delete_use_case() -> AsyncMock:
    uc = AsyncMock(spec=DeleteStoreFileUseCase)
    uc.execute = AsyncMock(return_value=None)
    return uc


@pytest.fixture(autouse=True)
def _override_dependencies(
    mock_list_use_case: AsyncMock,
    mock_get_use_case: AsyncMock,
    mock_put_use_case: AsyncMock,
    mock_delete_use_case: AsyncMock,
):
    """Wire mocked use cases via app.dependency_overrides and bypass auth.

    The protected router now depends on ``verify_credentials`` (dual JWT /
    API-key) instead of the master-key ``verify_api_key``. We override it to a
    fixed AuthContext so the route handlers run without real auth. The auth
    behaviour itself is covered by ``test_verify_credentials_wiring.py``.
    """
    from src.domain.entities.auth.auth_context import AuthContext

    app.dependency_overrides[security.verify_credentials] = lambda: AuthContext(
        user_id="test-user", method="api_key", raw_credential=""
    )
    app.dependency_overrides[get_list_store_files_use_case] = lambda: mock_list_use_case
    app.dependency_overrides[get_get_store_file_use_case] = lambda: mock_get_use_case
    app.dependency_overrides[get_put_store_file_use_case] = lambda: mock_put_use_case
    app.dependency_overrides[get_delete_store_file_use_case] = lambda: mock_delete_use_case

    yield

    app.dependency_overrides.clear()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# -- GET /api/v1/store/files (list) --------------------------------------------


class TestListStoreFilesRoute:
    """Tests for GET /api/v1/store/files?prefix=..."""

    async def test_list_returns_200_with_file_paths(self, client: AsyncClient, mock_list_use_case: AsyncMock) -> None:
        # Arrange
        mock_list_use_case.execute = AsyncMock(return_value=["/skills/rag/SKILL.md", "/skills/code-review/SKILL.md"])

        # Act
        resp = await client.get("/api/v1/store/files", params={"prefix": "/skills/"})

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body == ["/skills/rag/SKILL.md", "/skills/code-review/SKILL.md"]
        mock_list_use_case.execute.assert_awaited_once_with(prefix="/skills/")

    async def test_list_returns_200_with_empty_list(self, client: AsyncClient, mock_list_use_case: AsyncMock) -> None:
        # Arrange
        mock_list_use_case.execute = AsyncMock(return_value=[])

        # Act
        resp = await client.get("/api/v1/store/files")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_uses_prefix_query_param(self, client: AsyncClient, mock_list_use_case: AsyncMock) -> None:
        # Arrange
        mock_list_use_case.execute = AsyncMock(return_value=["/memories/AGENTS.md"])

        # Act
        resp = await client.get("/api/v1/store/files", params={"prefix": "/memories/"})

        # Assert
        assert resp.status_code == 200
        mock_list_use_case.execute.assert_awaited_once_with(prefix="/memories/")

    async def test_list_defaults_prefix_when_not_provided(
        self, client: AsyncClient, mock_list_use_case: AsyncMock
    ) -> None:
        # Arrange — when no prefix is given, the route should still call the use case
        mock_list_use_case.execute = AsyncMock(return_value=[])

        # Act
        resp = await client.get("/api/v1/store/files")

        # Assert
        assert resp.status_code == 200
        mock_list_use_case.execute.assert_awaited_once()

    async def test_list_storage_error_returns_503(self, client: AsyncClient, mock_list_use_case: AsyncMock) -> None:
        # Arrange
        mock_list_use_case.execute = AsyncMock(side_effect=StorageError("store unavailable"))

        # Act
        resp = await client.get("/api/v1/store/files")

        # Assert
        assert resp.status_code == 503
        assert "detail" in resp.json()


# -- GET /api/v1/store/files/{path} (get) --------------------------------------


class TestGetStoreFileRoute:
    """Tests for GET /api/v1/store/files/{path:path}."""

    async def test_get_returns_200_with_path_and_content(
        self, client: AsyncClient, mock_get_use_case: AsyncMock
    ) -> None:
        # Arrange
        mock_get_use_case.execute = AsyncMock(return_value="# My Skill")

        # Act
        resp = await client.get("/api/v1/store/files/skills/rag/SKILL.md")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "/skills/rag/SKILL.md"
        assert body["content"] == "# My Skill"
        mock_get_use_case.execute.assert_awaited_once_with(path="/skills/rag/SKILL.md")

    async def test_get_returns_404_when_file_not_found(self, client: AsyncClient, mock_get_use_case: AsyncMock) -> None:
        # Arrange — use case returns None for missing file
        mock_get_use_case.execute = AsyncMock(return_value=None)

        # Act
        resp = await client.get("/api/v1/store/files/skills/nonexistent/SKILL.md")

        # Assert
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_get_supports_nested_paths(self, client: AsyncClient, mock_get_use_case: AsyncMock) -> None:
        # Arrange
        mock_get_use_case.execute = AsyncMock(return_value="nested content")

        # Act
        resp = await client.get("/api/v1/store/files/skills/rag/sub/deep/SKILL.md")

        # Assert
        assert resp.status_code == 200
        assert resp.json()["path"] == "/skills/rag/sub/deep/SKILL.md"

    async def test_get_storage_error_returns_503(self, client: AsyncClient, mock_get_use_case: AsyncMock) -> None:
        # Arrange
        mock_get_use_case.execute = AsyncMock(side_effect=StorageError("store unavailable"))

        # Act
        resp = await client.get("/api/v1/store/files/any.md")

        # Assert
        assert resp.status_code == 503


# -- PUT /api/v1/store/files/{path} (create/replace) ---------------------------


class TestPutStoreFileRoute:
    """Tests for PUT /api/v1/store/files/{path:path}."""

    async def test_put_returns_200_with_path_and_content(
        self, client: AsyncClient, mock_put_use_case: AsyncMock
    ) -> None:
        # Arrange
        content = "# My Skill"
        mock_put_use_case.execute = AsyncMock(return_value=content)

        # Act
        resp = await client.put("/api/v1/store/files/skills/rag/SKILL.md", json={"content": content})

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "/skills/rag/SKILL.md"
        assert body["content"] == content
        mock_put_use_case.execute.assert_awaited_once_with(path="/skills/rag/SKILL.md", content=content)

    async def test_put_creates_new_file(self, client: AsyncClient, mock_put_use_case: AsyncMock) -> None:
        # Arrange
        mock_put_use_case.execute = AsyncMock(return_value="new content")

        # Act
        resp = await client.put("/api/v1/store/files/skills/new/SKILL.md", json={"content": "new content"})

        # Assert
        assert resp.status_code == 200
        assert resp.json()["content"] == "new content"

    async def test_put_replaces_existing_file(self, client: AsyncClient, mock_put_use_case: AsyncMock) -> None:
        # Arrange
        mock_put_use_case.execute = AsyncMock(return_value="updated content")

        # Act
        resp = await client.put("/api/v1/store/files/skills/rag/SKILL.md", json={"content": "updated content"})

        # Assert
        assert resp.status_code == 200
        assert resp.json()["content"] == "updated content"

    async def test_put_missing_content_body_returns_422(
        self, client: AsyncClient, mock_put_use_case: AsyncMock
    ) -> None:
        # Arrange
        # Act — body without required "content" field
        resp = await client.put("/api/v1/store/files/skills/rag/SKILL.md", json={})

        # Assert
        assert resp.status_code == 422
        mock_put_use_case.execute.assert_not_awaited()

    async def test_put_empty_body_returns_422(self, client: AsyncClient, mock_put_use_case: AsyncMock) -> None:
        # Arrange
        # Act — no JSON body at all
        resp = await client.put("/api/v1/store/files/skills/rag/SKILL.md")

        # Assert
        assert resp.status_code == 422
        mock_put_use_case.execute.assert_not_awaited()

    async def test_put_storage_error_returns_503(self, client: AsyncClient, mock_put_use_case: AsyncMock) -> None:
        # Arrange
        mock_put_use_case.execute = AsyncMock(side_effect=StorageError("store unavailable"))

        # Act
        resp = await client.put("/api/v1/store/files/any.md", json={"content": "x"})

        # Assert
        assert resp.status_code == 503


# -- DELETE /api/v1/store/files/{path} -----------------------------------------


class TestDeleteStoreFileRoute:
    """Tests for DELETE /api/v1/store/files/{path:path}."""

    async def test_delete_returns_204_when_file_exists(
        self, client: AsyncClient, mock_delete_use_case: AsyncMock
    ) -> None:
        # Arrange
        mock_delete_use_case.execute = AsyncMock(return_value=None)

        # Act
        resp = await client.delete("/api/v1/store/files/skills/rag/SKILL.md")

        # Assert
        assert resp.status_code == 204
        assert resp.content == b""
        mock_delete_use_case.execute.assert_awaited_once_with(path="/skills/rag/SKILL.md")

    async def test_delete_returns_404_when_file_not_found(
        self, client: AsyncClient, mock_delete_use_case: AsyncMock
    ) -> None:
        # Arrange — use case raises the real domain error that the route maps to 404.
        from src.domain.errors.store_file import StoreFileNotFoundError

        mock_delete_use_case.execute = AsyncMock(side_effect=StoreFileNotFoundError("not found"))

        # Act
        resp = await client.delete("/api/v1/store/files/skills/nonexistent/SKILL.md")

        # Assert
        assert resp.status_code == 404
        assert "detail" in resp.json()

    async def test_delete_storage_error_returns_503(self, client: AsyncClient, mock_delete_use_case: AsyncMock) -> None:
        # Arrange
        mock_delete_use_case.execute = AsyncMock(side_effect=StorageError("store unavailable"))

        # Act
        resp = await client.delete("/api/v1/store/files/any.md")

        # Assert
        assert resp.status_code == 503


# -- GET /api/v1/store/skills/{skill_name}/usage --------------------------------


class TestSkillUsageRoute:
    """Tests for GET /api/v1/store/skills/{skill_name}/usage."""

    async def test_returns_agents_using_skill(self, client: AsyncClient, mock_list_use_case: AsyncMock) -> None:
        # Arrange
        mock_list_use_case.execute = AsyncMock(
            return_value=[
                "/agents/agent-a/skills/mcp/SKILL.md",
                "/agents/agent-b/skills/mcp/SKILL.md",
                "/agents/agent-c/skills/rag/SKILL.md",
            ]
        )

        # Act
        resp = await client.get("/api/v1/store/skills/mcp/usage")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == ["agent-a", "agent-b"]

    async def test_returns_empty_when_no_agents_use_skill(
        self, client: AsyncClient, mock_list_use_case: AsyncMock
    ) -> None:
        # Arrange
        mock_list_use_case.execute = AsyncMock(
            return_value=[
                "/agents/agent-a/skills/rag/SKILL.md",
            ]
        )

        # Act
        resp = await client.get("/api/v1/store/skills/mcp/usage")

        # Assert
        assert resp.status_code == 200
        assert resp.json() == []
