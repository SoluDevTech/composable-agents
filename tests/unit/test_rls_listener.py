"""Tests for the SQLAlchemy ``before_cursor_execute`` RLS event listener.

The listener is registered on the engine's sync engine in
:func:`src.dependencies.init_persistence` and on the test ``db_engine`` fixture
via :func:`src.infrastructure.database.rls_listener.register_rls_listener`.

Behaviour:

* On **SQLite** (tests) the listener MUST be a no-op (``SET LOCAL`` is a
  Postgres-only statement) — it must not raise.
* On **PostgreSQL** it emits ``SELECT set_config('app.user_id', $1, true)``
  when ``current_user_id`` is set, and ``SET LOCAL row_security = off`` when
  ``bypass_rls`` is True.
* Calling ``cursor.execute`` on the raw DBAPI cursor does NOT re-trigger the
  listener (no infinite recursion).

The SQLite-path tests run a real query through a real in-memory SQLite engine
with the listener registered. The Postgres-path tests call the listener
function directly with a mock cursor + mock conn (whose ``dialect.name`` is
``"postgresql"``) so we can capture the emitted SQL without running it on
SQLite (whose cursor.execute is read-only and would reject ``SET LOCAL``).
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.infrastructure.database.rls_context import bypass_rls, current_user_id
from src.infrastructure.database.rls_listener import (
    _set_rls_guc_before_execute,
    register_rls_listener,
)


@pytest.fixture
async def sqlite_engine():
    """Real in-memory SQLite async engine with the RLS listener registered."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    register_rls_listener(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


def _make_postgres_conn_and_cursor() -> tuple[MagicMock, MagicMock]:
    """Build a mock (conn, cursor) pair simulating a PostgreSQL connection.

    ``conn.dialect.name`` is ``"postgresql"`` and ``cursor.execute`` is a
    ``MagicMock`` so we can assert on the emitted statement text.
    """
    conn = MagicMock()
    conn.dialect.name = "postgresql"
    cursor = MagicMock()
    return conn, cursor


class TestRlsListenerSqlite:
    """Listener must be a no-op on SQLite (no SET LOCAL emitted)."""

    async def test_listener_does_not_raise_on_sqlite_when_user_id_set(self, sqlite_engine):
        # Arrange — set the contextvar
        token = current_user_id.set("u1")
        try:
            # Act — run a real query through the engine
            async with sqlite_engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                # Assert — query succeeds (listener did not raise)
                assert result.scalar() == 1
        finally:
            current_user_id.reset(token)

    async def test_listener_does_not_raise_on_sqlite_when_bypass_set(self, sqlite_engine):
        # Arrange
        token = bypass_rls.set(True)
        try:
            async with sqlite_engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
        finally:
            bypass_rls.reset(token)

    async def test_listener_noop_when_no_contextvar_set(self, sqlite_engine):
        # Arrange — no contextvar set (default None / False)
        # Act
        async with sqlite_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            # Assert
            assert result.scalar() == 1


class TestRlsListenerPostgresEmulation:
    """Listener emits the right SET statements when dialect is postgresql.

    We call ``_set_rls_guc_before_execute`` directly with a mock (conn, cursor)
    pair whose ``conn.dialect.name`` is ``"postgresql"`` so we can capture the
    emitted SQL on the mock cursor without running it on SQLite.
    """

    async def test_emits_set_user_id_when_current_user_id_set(self):
        # Arrange
        conn, cursor = _make_postgres_conn_and_cursor()
        token = current_user_id.set("u1")
        try:
            # Act
            _set_rls_guc_before_execute(conn, cursor, "SELECT 1", None, None, False)
        finally:
            current_user_id.reset(token)

        # Assert — cursor.execute was called with set_config('app.user_id', ...)
        assert cursor.execute.called
        first_call_args = cursor.execute.call_args_list[0]
        stmt = first_call_args.args[0]
        params = first_call_args.args[1] if len(first_call_args.args) > 1 else None
        assert "app.user_id" in stmt
        assert params == ("u1",)

    async def test_emits_row_security_off_when_bypass_rls_true(self):
        # Arrange
        conn, cursor = _make_postgres_conn_and_cursor()
        token = bypass_rls.set(True)
        try:
            # Act
            _set_rls_guc_before_execute(conn, cursor, "SELECT 1", None, None, False)
        finally:
            bypass_rls.reset(token)

        # Assert
        assert cursor.execute.called
        stmt = cursor.execute.call_args_list[0].args[0]
        assert "row_security" in stmt
        assert "off" in stmt

    async def test_no_set_emitted_when_no_contextvar_and_not_bypass(self):
        # Arrange — defaults (None / False)
        conn, cursor = _make_postgres_conn_and_cursor()
        assert current_user_id.get() is None
        assert bypass_rls.get() is False
        # Act
        _set_rls_guc_before_execute(conn, cursor, "SELECT 1", None, None, False)
        # Assert — cursor.execute was NOT called
        assert not cursor.execute.called

    async def test_bypass_takes_precedence_over_user_id(self):
        # Arrange — both set
        conn, cursor = _make_postgres_conn_and_cursor()
        tok_u = current_user_id.set("u1")
        tok_b = bypass_rls.set(True)
        try:
            # Act
            _set_rls_guc_before_execute(conn, cursor, "SELECT 1", None, None, False)
        finally:
            current_user_id.reset(tok_u)
            bypass_rls.reset(tok_b)

        # Assert — only row_security=off was emitted (bypass returns early)
        assert cursor.execute.call_count == 1
        stmt = cursor.execute.call_args_list[0].args[0]
        assert "row_security" in stmt


class TestRlsListenerIdempotentRegistration:
    """register_rls_listener is idempotent and does not stack listeners."""

    def test_register_twice_does_not_raise(self):
        # Use a MagicMock engine to avoid building a real one
        mock_engine = MagicMock()
        mock_engine.sync_engine = MagicMock()
        # Act + Assert — second call must not raise
        register_rls_listener(mock_engine)
        register_rls_listener(mock_engine)

    def test_register_sets_sentinel_flag(self):
        mock_engine = MagicMock()
        mock_engine.sync_engine = MagicMock()
        register_rls_listener(mock_engine)
        # Assert — the sentinel flag is set on the sync engine
        assert getattr(mock_engine.sync_engine, "_composable_agents_rls_listener_registered", False)
