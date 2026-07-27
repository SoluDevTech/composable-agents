"""Tests for the API-key management use cases.

Uses the real :class:`PostgresApiKeyRepository` (via the shared in-memory
SQLite ``db_engine`` fixture). No internal component is mocked.

The use cases (``CreateApiKeyUseCase``, ``ListApiKeysUseCase``,
``RevokeApiKeyUseCase``), the entities (``CreatedApiKey``, ``ApiKeyView``) and
the domain error (``ApiKeyError``) do not exist yet, so these tests fail at
import until the green-phase implementation.
"""

import hashlib

import pytest

from src.application.use_cases.api_key.create_api_key import CreateApiKeyUseCase
from src.application.use_cases.api_key.list_api_keys import ListApiKeysUseCase
from src.application.use_cases.api_key.revoke_api_key import RevokeApiKeyUseCase
from src.domain.entities.auth.api_key import ApiKeyView, CreatedApiKey
from src.domain.errors.security import ApiKeyError, ApiKeyNotFoundError
from src.infrastructure.database.models.api_key import ApiKeyModel
from src.infrastructure.postgres_api_key.adapter import PostgresApiKeyRepository

_USER_A = "user-aaa"
_USER_B = "user-bbb"


@pytest.fixture
async def api_key_repo(db_engine) -> PostgresApiKeyRepository:
    """Provide a real PostgresApiKeyRepository backed by in-memory SQLite."""
    return PostgresApiKeyRepository(engine=db_engine)


@pytest.fixture
def create_use_case(api_key_repo) -> CreateApiKeyUseCase:
    return CreateApiKeyUseCase(repo=api_key_repo)


@pytest.fixture
def list_use_case(api_key_repo) -> ListApiKeysUseCase:
    return ListApiKeysUseCase(repo=api_key_repo)


@pytest.fixture
def revoke_use_case(api_key_repo) -> RevokeApiKeyUseCase:
    return RevokeApiKeyUseCase(repo=api_key_repo)


class TestCreateApiKeyUseCase:
    """Tests for ``CreateApiKeyUseCase.execute``."""

    async def test_returns_created_api_key_with_cpk_prefix_and_prefix_field(self, create_use_case):
        # Act
        result = await create_use_case.execute(user_id=_USER_A, name="my key")

        # Assert
        assert isinstance(result, CreatedApiKey)
        assert result.name == "my key"
        assert result.plaintext.startswith("cpk_")
        assert result.key_prefix == result.plaintext[:10]
        assert result.id  # non-empty uuid
        assert result.created_at is not None

    async def test_persists_row_with_sha256_of_plaintext(self, create_use_case, db_engine):
        # Act
        result = await create_use_case.execute(user_id=_USER_A, name="my key")

        # Assert — the stored hash equals sha256(plaintext)
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            row = await session.execute(select(ApiKeyModel).where(ApiKeyModel.id == result.id))
            model = row.scalar_one()
        expected_hash = hashlib.sha256(result.plaintext.encode()).hexdigest()
        assert model.key_hash == expected_hash
        assert model.user_id == _USER_A
        assert model.name == "my key"
        assert model.key_prefix == result.plaintext[:10]

    async def test_empty_name_raises_api_key_error(self, create_use_case):
        # Act & Assert
        with pytest.raises(ApiKeyError):
            await create_use_case.execute(user_id=_USER_A, name="")

    async def test_whitespace_name_raises_api_key_error(self, create_use_case):
        # Act & Assert
        with pytest.raises(ApiKeyError):
            await create_use_case.execute(user_id=_USER_A, name="   ")


class TestListApiKeysUseCase:
    """Tests for ``ListApiKeysUseCase.execute``."""

    async def test_returns_api_key_views_without_hash(self, list_use_case, create_use_case):
        # Arrange
        await create_use_case.execute(user_id=_USER_A, name="first")

        # Act
        result = await list_use_case.execute(user_id=_USER_A)

        # Assert
        assert len(result) == 1
        assert all(isinstance(v, ApiKeyView) for v in result)
        assert not hasattr(result[0], "key_hash")
        assert result[0].name == "first"

    async def test_includes_revoked_keys(self, list_use_case, create_use_case, revoke_use_case):
        # Arrange
        created = await create_use_case.execute(user_id=_USER_A, name="to-revoke")
        await revoke_use_case.execute(user_id=_USER_A, key_id=created.id)
        await create_use_case.execute(user_id=_USER_A, name="active")

        # Act
        result = await list_use_case.execute(user_id=_USER_A)

        # Assert — both the revoked and the active key appear
        assert len(result) == 2
        names = {v.name for v in result}
        assert names == {"to-revoke", "active"}
        # The revoked one carries revoked_at
        revoked_view = next(v for v in result if v.name == "to-revoke")
        assert revoked_view.revoked_at is not None

    async def test_does_not_leak_other_users_keys(self, list_use_case, create_use_case):
        # Arrange
        await create_use_case.execute(user_id=_USER_A, name="a")
        await create_use_case.execute(user_id=_USER_B, name="b")

        # Act
        result = await list_use_case.execute(user_id=_USER_A)

        # Assert
        assert len(result) == 1
        assert result[0].name == "a"


class TestRevokeApiKeyUseCase:
    """Tests for ``RevokeApiKeyUseCase.execute``."""

    async def test_revoke_sets_revoked_at(self, revoke_use_case, create_use_case, db_engine):
        # Arrange
        created = await create_use_case.execute(user_id=_USER_A, name="k")

        # Act
        await revoke_use_case.execute(user_id=_USER_A, key_id=created.id)

        # Assert
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            row = await session.execute(select(ApiKeyModel.revoked_at).where(ApiKeyModel.id == created.id))
        assert row.scalar_one() is not None

    async def test_revoke_unknown_key_raises_not_found(self, revoke_use_case):
        # Act & Assert
        from uuid import uuid4

        with pytest.raises(ApiKeyNotFoundError):
            await revoke_use_case.execute(user_id=_USER_A, key_id=uuid4().hex)

    async def test_revoke_other_user_key_raises_not_found(self, revoke_use_case, create_use_case):
        # Arrange — key owned by user B
        created = await create_use_case.execute(user_id=_USER_B, name="k")

        # Act & Assert — user A cannot revoke it
        with pytest.raises(ApiKeyNotFoundError):
            await revoke_use_case.execute(user_id=_USER_A, key_id=created.id)
