"""Tests for Settings database_url normalization, sslmode extraction, and statement_cache_size.

Verifies that any standard PostgreSQL connection string (postgresql://, postgres://,
or already-asyncpg) is normalized to postgresql+asyncpg:// for SQLAlchemy async,
with sslmode extracted and stripped (asyncpg doesn't accept it as a query param).
"""

import pytest
from pydantic import ValidationError

from src.config import Settings

_DUMMY_URL = "postgresql://user:pass@host:5432/db"


class TestDatabaseUrlNormalization:
    def test_postgresql_scheme_normalized_to_asyncpg(self):
        settings = Settings(database_url="postgresql://user:pass@host:5432/db")
        assert settings.database_url == "postgresql+asyncpg://user:pass@host:5432/db"

    def test_postgres_scheme_normalized_to_asyncpg(self):
        settings = Settings(database_url="postgres://user:pass@host:5432/db")
        assert settings.database_url == "postgresql+asyncpg://user:pass@host:5432/db"

    def test_already_asyncpg_scheme_unchanged(self):
        url = "postgresql+asyncpg://user:pass@host:5432/db"
        settings = Settings(database_url=url)
        assert settings.database_url == url

    def test_sslmode_and_channel_binding_stripped_from_url(self):
        settings = Settings(
            database_url="postgresql://neondb_owner:password@ep-xxx.neon.tech/neondb?sslmode=require&channel_binding=require"
        )
        assert settings.database_url == (
            "postgresql+asyncpg://neondb_owner:password@ep-xxx.neon.tech/neondb"
        )

    def test_sslmode_extracted_to_property(self):
        settings = Settings(
            database_url="postgresql://user:pass@host:5432/db?sslmode=require"
        )
        assert settings.ssl_mode == "require"

    def test_no_sslmode_returns_none(self):
        settings = Settings(database_url="postgresql://user:pass@host:5432/db")
        assert settings.ssl_mode is None

    def test_missing_database_url_raises_validation_error(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValidationError):
            Settings()

    def test_other_query_params_preserved(self):
        settings = Settings(
            database_url="postgresql://user:pass@host:5432/db?sslmode=require&application_name=myapp"
        )
        assert "application_name=myapp" in settings.database_url
        assert "sslmode" not in settings.database_url


class TestPostgresStatementCacheSize:
    def test_default_is_none(self):
        settings = Settings(database_url=_DUMMY_URL)
        assert settings.postgres_statement_cache_size is None

    def test_can_set_to_zero_for_poolers(self):
        settings = Settings(database_url=_DUMMY_URL, postgres_statement_cache_size=0)
        assert settings.postgres_statement_cache_size == 0

    def test_can_set_to_custom_value(self):
        settings = Settings(database_url=_DUMMY_URL, postgres_statement_cache_size=50)
        assert settings.postgres_statement_cache_size == 50
