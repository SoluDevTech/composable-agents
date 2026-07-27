"""Context variables for per-request RLS isolation.

These contextvars are set by ``ComposableAgentsSecurity.verify_credentials``
after a successful authentication and consumed by the SQLAlchemy
``before_cursor_execute`` event listener on the engine to set PostgreSQL GUCs
(``app.user_id``) so that Row-Level Security policies can filter rows per
authenticated user.

``current_credential`` holds the raw credential (JWT token or API key) for
audit logging without re-reading the request headers.

``current_auth_method`` records which authentication method produced the
context (``"jwt"`` or ``"api_key"``). It is consumed by the MCP credential
propagation resolver to decide which outgoing header placeholder
(``${USER_JWT}`` / ``${USER_API_KEY}``) to fill with ``current_credential``.

``bypass_rls`` is set to ``True`` by the ``system_rls_context`` async context
manager so that background jobs (cron, migrations) can read across all users
without an authenticated principal.
"""

import contextvars
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.auth.auth_context import AuthContext

current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_user_id", default=None)
current_credential: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_credential", default=None)
# Authentication method that produced the current context ("jwt" or "api_key").
# Set by ``ComposableAgentsSecurity.verify_credentials`` alongside
# ``current_user_id`` / ``current_credential``. Consumed by the MCP credential
# propagation resolver (``${USER_JWT}`` / ``${USER_API_KEY}``) to decide which
# credential placeholder to fill.
current_auth_method: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_auth_method", default=None)
# Full AuthContext resolved for the current request (carries email/name/username
# propagated from the JWT when available). Set by
# ``ComposableAgentsSecurity.verify_credentials`` and consumed by the
# ``get_current_auth_context`` FastAPI dependency (e.g. ``GET /api/v1/users/me``).
current_auth_context: contextvars.ContextVar["AuthContext | None"] = contextvars.ContextVar(
    "current_auth_context", default=None
)
# When True, the RLS event listener emits ``SET LOCAL row_security = off`` so
# that system/migration queries can read across all users.
bypass_rls: contextvars.ContextVar[bool] = contextvars.ContextVar("bypass_rls", default=False)


@asynccontextmanager
async def system_rls_context() -> AsyncIterator[None]:
    """Temporarily disable RLS for the duration of a system / migration block.

    Background jobs and migrations run without an authenticated user and
    therefore have no ``current_user_id``. Without this context, RLS policies
    would filter out every row (``user_id = NULL`` is always FALSE).

    Usage::

        async with system_rls_context():
            await run_migrations()

    The ``bypass_rls`` contextvar is reset on exit, including when an exception
    propagates out of the ``with`` block.
    """
    token = bypass_rls.set(True)
    try:
        yield
    finally:
        bypass_rls.reset(token)
