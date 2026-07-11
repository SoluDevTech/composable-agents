"""Tests for connect_args assembly in dependencies.init_persistence.

Covers the SSL context branch and statement_cache_size propagation — the most
subtle code in dependencies.py. Uses monkeypatch to intercept create_async_engine
and inspect the connect_args without needing a real PostgreSQL or MinIO.
"""

import ssl
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.dependencies import init_persistence, reset


@pytest.fixture
def captured_engine(monkeypatch):
    """Patch create_async_engine so we can inspect connect_args without a real DB."""
    captured: dict = {}
    dummy_engine = MagicMock()
    dummy_engine.dispose = AsyncMock()

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured["connect_args"] = kwargs.get("connect_args", {})
        return dummy_engine

    monkeypatch.setattr("src.dependencies.create_async_engine", fake_create_async_engine)

    # Patch MinioAgentConfigStore to avoid network calls
    mock_store = MagicMock()
    mock_store.ensure_bucket = AsyncMock()
    monkeypatch.setattr("src.dependencies.MinioAgentConfigStore", lambda **_: mock_store)

    return captured


@pytest.fixture
def patch_settings(monkeypatch):
    """Patch src.dependencies.settings with a Settings instance built from env."""

    def _apply(**env_overrides):
        from src.config import Settings

        env_defaults = {
            "DATABASE_URL": "postgresql://user:pass@host:5432/db",
            "MINIO_ENDPOINT": "localhost:9040",
            "MINIO_ACCESS_KEY": "minioadmin",
            "MINIO_SECRET_KEY": "minioadmin",
            "MINIO_BUCKET": "test-bucket",
            "MINIO_SECURE": "false",
        }
        env_defaults.update(env_overrides)
        for k, v in env_defaults.items():
            monkeypatch.setenv(k, v)

        test_settings = Settings()
        monkeypatch.setattr("src.dependencies.settings", test_settings)
        return test_settings

    return _apply


class TestConnectArgsSslModes:
    """Parametrized test over the four sslmode values that produce an SSL context."""

    @pytest.mark.parametrize(
        "ssl_mode",
        ["require", "prefer", "verify-ca", "verify-full"],
    )
    async def test_ssl_context_attached(self, captured_engine, patch_settings, ssl_mode):
        url = f"postgresql://user:pass@host:5432/db?sslmode={ssl_mode}"
        patch_settings(DATABASE_URL=url)

        reset()
        await init_persistence()

        connect_args = captured_engine["connect_args"]
        assert "ssl" in connect_args, f"ssl context missing for sslmode={ssl_mode}"
        assert isinstance(connect_args["ssl"], ssl.SSLContext)

    async def test_disable_no_ssl_context(self, captured_engine, patch_settings):
        patch_settings(DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=disable")

        reset()
        await init_persistence()

        assert "ssl" not in captured_engine["connect_args"]

    async def test_allow_no_ssl_context(self, captured_engine, patch_settings):
        patch_settings(DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=allow")

        reset()
        await init_persistence()

        assert "ssl" not in captured_engine["connect_args"]

    async def test_no_sslmode_no_ssl_context(self, captured_engine, patch_settings):
        patch_settings(DATABASE_URL="postgresql://user:pass@host:5432/db")

        reset()
        await init_persistence()

        assert "ssl" not in captured_engine["connect_args"]


class TestSslContextSecurityProperties:
    """Verify the SSL context has the right verification flags per mode."""

    async def test_verify_full_has_hostname_and_cert_verification(self, captured_engine, patch_settings):
        patch_settings(DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=verify-full")

        reset()
        await init_persistence()

        ctx = captured_engine["connect_args"]["ssl"]
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    async def test_verify_ca_has_cert_verification(self, captured_engine, patch_settings):
        patch_settings(DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=verify-ca")

        reset()
        await init_persistence()

        ctx = captured_engine["connect_args"]["ssl"]
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    async def test_require_no_cert_verification(self, captured_engine, patch_settings):
        patch_settings(DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=require")

        reset()
        await init_persistence()

        ctx = captured_engine["connect_args"]["ssl"]
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE

    async def test_prefer_no_cert_verification(self, captured_engine, patch_settings):
        patch_settings(DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=prefer")

        reset()
        await init_persistence()

        ctx = captured_engine["connect_args"]["ssl"]
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE


class TestStatementCacheSizePropagation:
    async def test_statement_cache_size_passed_when_set(self, captured_engine, patch_settings):
        patch_settings(
            DATABASE_URL="postgresql://user:pass@host:5432/db",
            POSTGRES_STATEMENT_CACHE_SIZE="0",
        )

        reset()
        await init_persistence()

        assert captured_engine["connect_args"]["statement_cache_size"] == 0

    async def test_statement_cache_size_omitted_when_none(self, captured_engine, patch_settings):
        patch_settings(DATABASE_URL="postgresql://user:pass@host:5432/db")

        reset()
        await init_persistence()

        assert "statement_cache_size" not in captured_engine["connect_args"]
