"""Tests for the PostgresUserLlmSettingsRepository against a real in-memory SQLite engine.

These tests drive the "LLM credentials per user" layer (TDD red phase). They
exercise the real :class:`PostgresUserLlmSettingsRepository` adapter against
the shared in-memory SQLite ``db_engine`` fixture — no mocks on internal
components. The :class:`FernetCrypto` dependency is real (fixed test key).
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user_llm_settings import UserLlmSettings
from src.infrastructure.crypto.fernet_crypto import FernetCrypto
from src.infrastructure.database.models.user_llm_setting import UserLlmSettingModel
from src.infrastructure.postgres_user_llm.adapter import PostgresUserLlmSettingsRepository

_USER_A = "user-aaa"
_USER_B = "user-bbb"

_PROVIDER = "openai"
_BASE_URL = "https://api.openai.com/v1"
_API_KEY_PLAINTEXT = "sk-test-123456789abcdef"
_TEST_KEY = "Yr5R5-6lRUaxEwZWVysIaFs5POHcLps2OZViwWAscaU="


@pytest.fixture
def crypto() -> FernetCrypto:
    return FernetCrypto(key=_TEST_KEY)


@pytest.fixture
async def repo(db_engine, crypto) -> PostgresUserLlmSettingsRepository:
    """Provide a real PostgresUserLlmSettingsRepository backed by in-memory SQLite."""
    return PostgresUserLlmSettingsRepository(engine=db_engine, crypto=crypto)


class TestGetAbsent:
    async def test_get_returns_none_when_no_settings(self, repo):
        result = await repo.get(_USER_A)
        assert result is None

    async def test_get_decrypted_returns_none_when_no_settings(self, repo):
        result = await repo.get_decrypted(_USER_A)
        assert result is None


class TestUpsertInsert:
    async def test_upsert_inserts_row_and_returns_settings(self, repo, db_engine, crypto):
        # Arrange — produce a real encrypted token
        api_key_encrypted = crypto.encrypt(_API_KEY_PLAINTEXT)

        # Act
        result = await repo.upsert(
            user_id=_USER_A,
            provider=_PROVIDER,
            base_url=_BASE_URL,
            api_key_encrypted=api_key_encrypted,
        )

        # Assert — return shape
        assert isinstance(result, UserLlmSettings)
        assert result.user_id == _USER_A
        assert result.provider == _PROVIDER
        assert result.base_url == _BASE_URL
        assert result.created_at is not None
        assert result.updated_at is not None

        # Assert — row persisted with the encrypted token (not the plaintext)
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            row = await session.execute(select(UserLlmSettingModel).where(UserLlmSettingModel.user_id == _USER_A))
            model = row.scalar_one()
        assert model.api_key_encrypted == api_key_encrypted
        assert model.api_key_encrypted != _API_KEY_PLAINTEXT


class TestGetReturnsMasked:
    async def test_get_returns_masked_not_full_plaintext(self, repo, crypto):
        # Arrange — upsert first with a real encrypted token
        await repo.upsert(
            user_id=_USER_A,
            provider=_PROVIDER,
            base_url=_BASE_URL,
            api_key_encrypted=crypto.encrypt(_API_KEY_PLAINTEXT),
        )

        # Act
        result = await repo.get(_USER_A)

        # Assert
        assert result is not None
        assert result.api_key_masked is not None
        # The masked value must NOT contain the full plaintext
        assert result.api_key_masked != _API_KEY_PLAINTEXT
        # Masked contains ellipsis
        assert "..." in result.api_key_masked


class TestUpsertUpdate:
    async def test_upsert_twice_updates_row_and_bumps_updated_at(self, repo, db_engine, crypto):
        # Arrange — first upsert
        first = await repo.upsert(
            user_id=_USER_A,
            provider=_PROVIDER,
            base_url=_BASE_URL,
            api_key_encrypted=crypto.encrypt("TOKEN-1"),
        )

        # Force a tiny time delta to be safe across clocks
        import asyncio

        await asyncio.sleep(0.01)

        # Act — second upsert updates
        second = await repo.upsert(
            user_id=_USER_A,
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key_encrypted=crypto.encrypt("TOKEN-2"),
        )

        # Assert — only one row, content updated, updated_at changed
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            rows = (
                (await session.execute(select(UserLlmSettingModel).where(UserLlmSettingModel.user_id == _USER_A)))
                .scalars()
                .all()
            )
        assert len(rows) == 1
        assert rows[0].provider == "openrouter"
        assert rows[0].base_url == "https://openrouter.ai/api/v1"
        assert rows[0].api_key_encrypted != "TOKEN-2"  # encrypted form
        assert second.updated_at >= first.updated_at


class TestGetDecrypted:
    async def test_get_decrypted_returns_base_url_and_plaintext(self, repo, crypto):
        # Arrange — upsert with a real encrypted token
        await repo.upsert(
            user_id=_USER_A,
            provider=_PROVIDER,
            base_url=_BASE_URL,
            api_key_encrypted=crypto.encrypt(_API_KEY_PLAINTEXT),
        )

        # Act
        result = await repo.get_decrypted(_USER_A)

        # Assert
        assert result is not None
        base_url, api_key = result
        assert base_url == _BASE_URL
        assert api_key == _API_KEY_PLAINTEXT


class TestDelete:
    async def test_delete_removes_row(self, repo, db_engine, crypto):
        # Arrange
        await repo.upsert(
            user_id=_USER_A,
            provider=_PROVIDER,
            base_url=_BASE_URL,
            api_key_encrypted=crypto.encrypt(_API_KEY_PLAINTEXT),
        )

        # Act
        await repo.delete(_USER_A)

        # Assert — row gone
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            row = await session.execute(select(UserLlmSettingModel).where(UserLlmSettingModel.user_id == _USER_A))
        assert row.scalar_one_or_none() is None
        assert await repo.get(_USER_A) is None

    async def test_delete_when_absent_is_noop(self, repo):
        # Act — should not raise
        await repo.delete(_USER_A)


class TestIsolation:
    async def test_settings_for_user_a_invisible_to_user_b(self, repo, crypto):
        # Arrange
        await repo.upsert(
            user_id=_USER_A,
            provider=_PROVIDER,
            base_url=_BASE_URL,
            api_key_encrypted=crypto.encrypt(_API_KEY_PLAINTEXT),
        )

        # Act — user B sees nothing
        assert await repo.get(_USER_B) is None
        assert await repo.get_decrypted(_USER_B) is None
