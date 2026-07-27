"""Tests for the PostgresApiKeyRepository against a real in-memory SQLite engine.

These tests drive the "API keys per user" layer (TDD red phase). They exercise
the real :class:`PostgresApiKeyRepository` adapter against the shared in-memory
SQLite ``db_engine`` fixture — no mocks on internal components.

The ORM model (``src.infrastructure.database.models.api_key.ApiKeyModel``), the
extended port (``src.domain.ports.auth.api_key_repository.ApiKeyRepository``)
and the adapter (``src.infrastructure.postgres_api_key.adapter.PostgresApiKeyRepository``)
do not exist yet, so these tests fail at import until the implementation is
added in the green phase.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.auth.api_key import ApiKeyView
from src.domain.errors.security import ApiKeyNotFoundError
from src.infrastructure.auth.api_key_hasher import ApiKeyHasher
from src.infrastructure.database.models.api_key import ApiKeyModel
from src.infrastructure.postgres_api_key.adapter import PostgresApiKeyRepository

_USER_A = "user-aaa"
_USER_B = "user-bbb"


@pytest.fixture
async def api_key_repo(db_engine) -> PostgresApiKeyRepository:
    """Provide a real PostgresApiKeyRepository backed by in-memory SQLite."""
    return PostgresApiKeyRepository(engine=db_engine)


async def _insert_key(
    db_engine,
    *,
    user_id: str,
    name: str,
    plaintext: str,
    revoked: bool = False,
) -> str:
    """Insert an ApiKeyModel row directly and return its id."""
    key_id = uuid4().hex
    key_hash = ApiKeyHasher.hash_key(plaintext)
    key_prefix = plaintext[:10]
    now = datetime.now(UTC)
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        session.add(
            ApiKeyModel(
                id=key_id,
                user_id=user_id,
                name=name,
                key_hash=key_hash,
                key_prefix=key_prefix,
                revoked_at=now if revoked else None,
                last_used_at=None,
                created_at=now,
            )
        )
        await session.commit()
    return key_id


class TestCreateApiKey:
    """Tests for ``PostgresApiKeyRepository.create``."""

    async def test_create_returns_key_id_and_persists_row(self, api_key_repo, db_engine):
        # Arrange
        plaintext = ApiKeyHasher.generate_key()
        key_hash = ApiKeyHasher.hash_key(plaintext)
        key_prefix = plaintext[:10]

        # Act
        key_id = await api_key_repo.create(
            user_id=_USER_A,
            name="my-key",
            key_hash=key_hash,
            key_prefix=key_prefix,
        )

        # Assert — returned id is a uuid hex
        assert isinstance(key_id, str)
        assert len(key_id) == 36 or len(key_id) == 32  # uuid4 hex (with/without dashes)

        # Assert — row exists with correct fields
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            model = await session.get(ApiKeyModel, key_id)
        assert model is not None
        assert model.user_id == _USER_A
        assert model.name == "my-key"
        assert model.key_hash == key_hash
        assert model.key_prefix == key_prefix
        assert model.revoked_at is None
        assert model.last_used_at is None
        assert model.created_at is not None


class TestFindActiveByHash:
    """Tests for ``PostgresApiKeyRepository.find_active_by_hash``."""

    async def test_returns_user_id_and_key_id_for_active_key(self, api_key_repo, db_engine):
        # Arrange
        plaintext = ApiKeyHasher.generate_key()
        key_id = await _insert_key(db_engine, user_id=_USER_A, name="k", plaintext=plaintext)
        key_hash = ApiKeyHasher.hash_key(plaintext)

        # Act
        result = await api_key_repo.find_active_by_hash(key_hash)

        # Assert
        assert result is not None
        assert result[0] == _USER_A
        assert result[1] == key_id

    async def test_returns_none_for_unknown_hash(self, api_key_repo):
        # Act
        result = await api_key_repo.find_active_by_hash("0" * 64)

        # Assert
        assert result is None

    async def test_returns_none_for_revoked_key(self, api_key_repo, db_engine):
        # Arrange
        plaintext = ApiKeyHasher.generate_key()
        await _insert_key(db_engine, user_id=_USER_A, name="k", plaintext=plaintext, revoked=True)
        key_hash = ApiKeyHasher.hash_key(plaintext)

        # Act
        result = await api_key_repo.find_active_by_hash(key_hash)

        # Assert
        assert result is None


class TestListByUser:
    """Tests for ``PostgresApiKeyRepository.list_by_user``."""

    async def test_returns_all_keys_for_user_sorted_by_created_at_desc(self, api_key_repo, db_engine):
        # Arrange — two active keys + one revoked key for user A
        await _insert_key(db_engine, user_id=_USER_A, name="first", plaintext="cpk_aaaaaaaa1")
        # Bump created_at of k2 to be later than k1 by updating it directly.
        k2 = await _insert_key(db_engine, user_id=_USER_A, name="second", plaintext="cpk_aaaaaaaa2")
        later = datetime.now(UTC) + timedelta(days=1)
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            await session.execute(update(ApiKeyModel).where(ApiKeyModel.id == k2).values(created_at=later))
            await session.commit()
        await _insert_key(db_engine, user_id=_USER_A, name="revoked", plaintext="cpk_aaaaaaaa3", revoked=True)

        # Act
        result = await api_key_repo.list_by_user(_USER_A)

        # Assert
        assert len(result) == 3
        assert all(isinstance(v, ApiKeyView) for v in result)
        # Sorted by created_at desc — k2 (later) first, then the other two.
        assert result[0].id == k2
        # Does NOT include the hash.
        assert not hasattr(result[0], "key_hash")

    async def test_returns_empty_list_for_unknown_user(self, api_key_repo):
        # Act
        result = await api_key_repo.list_by_user("nobody")

        # Assert
        assert result == []

    async def test_does_not_leak_other_users_keys(self, api_key_repo, db_engine):
        # Arrange
        await _insert_key(db_engine, user_id=_USER_A, name="a", plaintext="cpk_bbbbbbbbb1")
        await _insert_key(db_engine, user_id=_USER_B, name="b", plaintext="cpk_bbbbbbbbb2")

        # Act
        result = await api_key_repo.list_by_user(_USER_A)

        # Assert — only user A's keys are returned
        assert len(result) == 1
        assert result[0].name == "a"


class TestRevoke:
    """Tests for ``PostgresApiKeyRepository.revoke``."""

    async def test_revoke_sets_revoked_at_for_existing_key(self, api_key_repo, db_engine):
        # Arrange
        plaintext = ApiKeyHasher.generate_key()
        key_id = await _insert_key(db_engine, user_id=_USER_A, name="k", plaintext=plaintext)

        # Act
        await api_key_repo.revoke(user_id=_USER_A, key_id=key_id)

        # Assert
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            model = await session.get(ApiKeyModel, key_id)
        assert model.revoked_at is not None

    async def test_revoke_unknown_key_id_raises_api_key_not_found(self, api_key_repo):
        # Act & Assert
        with pytest.raises(ApiKeyNotFoundError):
            await api_key_repo.revoke(user_id=_USER_A, key_id=uuid4().hex)

    async def test_revoke_other_user_key_raises_api_key_not_found(self, api_key_repo, db_engine):
        # Arrange — a key owned by user B
        plaintext = ApiKeyHasher.generate_key()
        key_id = await _insert_key(db_engine, user_id=_USER_B, name="k", plaintext=plaintext)

        # Act & Assert — user A cannot revoke user B's key
        with pytest.raises(ApiKeyNotFoundError):
            await api_key_repo.revoke(user_id=_USER_A, key_id=key_id)

    async def test_revoke_already_revoked_key_is_idempotent_success(self, api_key_repo, db_engine):
        # Arrange
        plaintext = ApiKeyHasher.generate_key()
        key_id = await _insert_key(db_engine, user_id=_USER_A, name="k", plaintext=plaintext)

        # Act — revoke twice; the second call is a no-op success
        await api_key_repo.revoke(user_id=_USER_A, key_id=key_id)
        await api_key_repo.revoke(user_id=_USER_A, key_id=key_id)

        # Assert
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            model = await session.get(ApiKeyModel, key_id)
        assert model.revoked_at is not None


class TestTouchLastUsed:
    """Tests for ``PostgresApiKeyRepository.touch_last_used``."""

    async def test_touch_last_used_sets_last_used_at(self, api_key_repo, db_engine):
        # Arrange
        plaintext = ApiKeyHasher.generate_key()
        key_id = await _insert_key(db_engine, user_id=_USER_A, name="k", plaintext=plaintext)

        # Act
        await api_key_repo.touch_last_used(key_id)

        # Assert
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            result = await session.execute(select(ApiKeyModel.last_used_at).where(ApiKeyModel.id == key_id))
        last_used = result.scalar_one()
        assert last_used is not None
