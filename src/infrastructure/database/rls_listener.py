"""SQLAlchemy ``before_cursor_execute`` event listener for PostgreSQL RLS.

Registers a listener on the engine's sync engine that, before each query,
emits transaction-scoped ``SET LOCAL`` GUCs from the
:mod:`src.infrastructure.database.rls_context` contextvars so that PostgreSQL
Row-Level Security policies can filter rows per authenticated user.

Behaviour:

* On **non-postgresql** dialects (SQLite in tests) the listener is a no-op —
  ``SET LOCAL`` is a Postgres-only statement and would raise on SQLite. The
  listener still runs (so it can be spied on) but does nothing.
* On **postgresql**:

  - If ``bypass_rls`` is ``True`` → emits ``SET LOCAL row_security = off`` so
    background jobs / migrations can read across all users.
  - Else if ``current_user_id`` is set → emits
    ``SELECT set_config('app.user_id', $1, true)`` (transaction-scoped).
  - Else (no contextvar, no bypass) → no-op.

Calling ``cursor.execute`` on the raw DBAPI cursor does **not** re-trigger
``before_cursor_execute`` (only SQLAlchemy's ``conn.execute`` fires it), so
there is no infinite recursion — this is the documented SQLAlchemy recipe
("Switching Databases").
"""

import logging

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from src.domain.logging.messages import LogMessage
from src.infrastructure.database.rls_context import bypass_rls, current_user_id

logger = logging.getLogger(__name__)

# Sentinel stored on the sync engine so register_rls_listener is idempotent.
_RLS_LISTENER_FLAG = "_composable_agents_rls_listener_registered"


def _set_rls_guc_before_execute(conn, cursor, _statement, _parameters, _context, _executemany) -> None:
    """Set PostgreSQL GUCs for RLS from contextvars before each query.

    Args:
        conn: SQLAlchemy connection (carries ``dialect``).
        cursor: Raw DBAPI cursor — ``cursor.execute`` does NOT re-trigger
            this event, so it is safe to emit ``SET LOCAL`` here.
        _statement: The SQL statement about to be executed (unused).
        _parameters: Bind parameters (unused).
        _context: SQLAlchemy execution context (unused).
        _executemany: Whether ``executemany`` is used (unused).
    """
    dialect_name = conn.dialect.name

    # SQLite (tests) — no-op. SET LOCAL would raise on SQLite.
    if dialect_name != "postgresql":
        return

    if bypass_rls.get():
        cursor.execute("SET LOCAL row_security = off")
        logger.debug(LogMessage.RLS_BYPASS_ENABLED)
        return

    uid = current_user_id.get()
    if not uid:
        return

    # Transaction-scoped (LOCAL) GUC. Using set_config(..., true) is equivalent
    # to SET LOCAL but parameterised, avoiding SQL injection.
    cursor.execute("SELECT set_config('app.user_id', $1, true)", (uid,))
    logger.debug(LogMessage.RLS_CONTEXT_SET, uid)


def register_rls_listener(engine: AsyncEngine) -> None:
    """Register the RLS ``before_cursor_execute`` listener on ``engine``.

    Idempotent: calling twice on the same engine does not stack a second
    listener (a sentinel flag is set on the sync engine).

    Args:
        engine: The async engine whose ``sync_engine`` will receive the
            listener.
    """
    sync_engine = engine.sync_engine
    if getattr(sync_engine, _RLS_LISTENER_FLAG, False):
        return
    event.listen(sync_engine, "before_cursor_execute", _set_rls_guc_before_execute)
    setattr(sync_engine, _RLS_LISTENER_FLAG, True)
