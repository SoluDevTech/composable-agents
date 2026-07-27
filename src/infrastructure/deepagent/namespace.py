"""Namespace resolution helper for per-user LangGraph Store isolation.

Builds a LangGraph Store namespace tuple prefixed by the current authenticated
user id (read from the ``current_user_id`` contextvar set by
``verify_credentials``). When the contextvar is ``None`` (no auth context,
e.g. existing tests, background jobs), the user prefix is dropped so the
namespace falls back to the legacy global tuple — keeping all pre-existing
tests green.

Usage::

    from src.infrastructure.deepagent.namespace import user_namespaced

    ns = user_namespaced("filesystem")  # ("u1", "filesystem") or ("filesystem",)
"""

from src.infrastructure.database.rls_context import current_user_id


def user_namespaced(*suffix: str) -> tuple[str, ...]:
    """Build a per-user-scoped namespace tuple for the LangGraph Store.

    Args:
        *suffix: Namespace suffix segments (e.g. ``"filesystem"``, or
            ``"agents", "agent1"``).

    Returns:
        ``(user_id, *suffix)`` when ``current_user_id`` is set, otherwise
        ``tuple(suffix)`` (legacy global namespace, preserving existing
        behaviour for tests and unauthenticated contexts).

    Examples:
        >>> user_namespaced("filesystem")  # with current_user_id="u1"
        ('u1', 'filesystem')
        >>> user_namespaced("filesystem")  # with current_user_id=None
        ('filesystem',)
    """
    uid = current_user_id.get()
    return (uid, *suffix) if uid else tuple(suffix)
