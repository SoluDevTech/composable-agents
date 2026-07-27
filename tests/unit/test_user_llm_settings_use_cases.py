"""Tests for the user-LLM-settings use cases.

Uses the real :class:`PostgresUserLlmSettingsRepository` (via the shared
in-memory SQLite ``db_engine`` fixture) and a real :class:`FernetCrypto` with a
fixed test key. No internal component is mocked.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.user_llm_settings.delete_user_llm_settings import (
    DeleteUserLlmSettingsUseCase,
)
from src.application.use_cases.user_llm_settings.get_user_llm_settings import (
    GetUserLlmSettingsUseCase,
)
from src.application.use_cases.user_llm_settings.resolve_user_llm_credentials import (
    ResolveUserLlmCredentialsUseCase,
)
from src.application.use_cases.user_llm_settings.upsert_user_llm_settings import (
    UpsertUserLlmSettingsUseCase,
)
from src.domain.entities.user_llm_settings import UserLlmSettings, UserLlmSettingsInput
from src.infrastructure.crypto.fernet_crypto import FernetCrypto
from src.infrastructure.database.models.user_llm_setting import UserLlmSettingModel
from src.infrastructure.postgres_user_llm.adapter import PostgresUserLlmSettingsRepository

_USER_A = "user-aaa"
_USER_B = "user-bbb"
_TEST_KEY = "Yr5R5-6lRUaxEwZWVysIaFs5POHcLps2OZViwWAscaU="


@pytest.fixture
def crypto() -> FernetCrypto:
    return FernetCrypto(key=_TEST_KEY)


@pytest.fixture
async def repo(db_engine, crypto) -> PostgresUserLlmSettingsRepository:
    return PostgresUserLlmSettingsRepository(engine=db_engine, crypto=crypto)


@pytest.fixture
def get_uc(repo) -> GetUserLlmSettingsUseCase:
    return GetUserLlmSettingsUseCase(repo=repo)


@pytest.fixture
def upsert_uc(repo, crypto) -> UpsertUserLlmSettingsUseCase:
    return UpsertUserLlmSettingsUseCase(repo=repo, crypto=crypto)


@pytest.fixture
def delete_uc(repo) -> DeleteUserLlmSettingsUseCase:
    return DeleteUserLlmSettingsUseCase(repo=repo)


@pytest.fixture
def resolve_uc(repo) -> ResolveUserLlmCredentialsUseCase:
    return ResolveUserLlmCredentialsUseCase(repo=repo)


class TestGetUserLlmSettings:
    async def test_get_returns_none_when_absent(self, get_uc):
        result = await get_uc.execute(_USER_A)
        assert result is None

    async def test_get_returns_settings_after_upsert(self, get_uc, upsert_uc):
        await upsert_uc.execute(
            user_id=_USER_A,
            inp=UserLlmSettingsInput(provider="openai", base_url="https://api.openai.com/v1", api_key="sk-test"),
        )
        result = await get_uc.execute(_USER_A)
        assert isinstance(result, UserLlmSettings)
        assert result.provider == "openai"
        assert result.base_url == "https://api.openai.com/v1"


class TestUpsertUserLlmSettings:
    async def test_upsert_encrypts_api_key_in_db(self, upsert_uc, db_engine):
        # Act
        result = await upsert_uc.execute(
            user_id=_USER_A,
            inp=UserLlmSettingsInput(provider="openai", base_url="https://api.openai.com/v1", api_key="sk-test-123"),
        )

        # Assert — returned settings carries masked key, NOT the plaintext
        assert isinstance(result, UserLlmSettings)
        assert result.api_key_masked is not None
        assert "sk-test-123" not in (result.api_key_masked or "")
        assert "..." in result.api_key_masked

        # Assert — DB stores an encrypted token that is NOT the plaintext
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            row = await session.execute(select(UserLlmSettingModel).where(UserLlmSettingModel.user_id == _USER_A))
            model = row.scalar_one()
        assert model.api_key_encrypted != "sk-test-123"
        assert model.provider == "openai"
        assert model.base_url == "https://api.openai.com/v1"

    async def test_upsert_twice_updates_settings(self, upsert_uc, db_engine):
        await upsert_uc.execute(
            user_id=_USER_A,
            inp=UserLlmSettingsInput(provider="openai", base_url="https://api.openai.com/v1", api_key="sk-1"),
        )
        await upsert_uc.execute(
            user_id=_USER_A,
            inp=UserLlmSettingsInput(provider="openrouter", base_url="https://openrouter.ai/v1", api_key="sk-2"),
        )
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            rows = (
                (await session.execute(select(UserLlmSettingModel).where(UserLlmSettingModel.user_id == _USER_A)))
                .scalars()
                .all()
            )
        assert len(rows) == 1
        assert rows[0].provider == "openrouter"


class TestDeleteUserLlmSettings:
    async def test_delete_removes_settings(self, delete_uc, upsert_uc, get_uc):
        await upsert_uc.execute(
            user_id=_USER_A,
            inp=UserLlmSettingsInput(provider="openai", base_url="x", api_key="sk-x"),
        )
        await delete_uc.execute(_USER_A)
        assert await get_uc.execute(_USER_A) is None

    async def test_delete_absent_is_noop(self, delete_uc):
        await delete_uc.execute(_USER_A)  # no raise


class TestResolveUserLlmCredentials:
    async def test_resolve_returns_none_when_absent(self, resolve_uc):
        result = await resolve_uc.execute(_USER_A)
        assert result is None

    async def test_resolve_returns_decrypted_tuple_after_upsert(self, resolve_uc, upsert_uc):
        await upsert_uc.execute(
            user_id=_USER_A,
            inp=UserLlmSettingsInput(provider="openai", base_url="https://api.openai.com/v1", api_key="sk-decrypt-me"),
        )
        result = await resolve_uc.execute(_USER_A)
        assert result is not None
        base_url, api_key = result
        assert base_url == "https://api.openai.com/v1"
        # The decrypted key equals the original plaintext
        assert api_key == "sk-decrypt-me"

    async def test_isolation_user_a_invisible_to_user_b(self, resolve_uc, upsert_uc):
        await upsert_uc.execute(
            user_id=_USER_A,
            inp=UserLlmSettingsInput(provider="openai", base_url="x", api_key="sk-a"),
        )
        assert await resolve_uc.execute(_USER_B) is None
