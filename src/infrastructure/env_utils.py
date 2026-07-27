"""Environment and user-credential variable resolution utilities.

``resolve_env_vars`` resolves ``${VAR_NAME}`` patterns using ``os.environ``
(keeping unresolved placeholders intact).

``resolve_all_vars`` resolves BOTH ``os.environ`` vars AND the user-credential
placeholders ``${USER_JWT}`` and ``${USER_API_KEY}`` in a single pass. The
user-credential placeholders are resolved from the RLS contextvars:

* ``${USER_JWT}``     → ``current_credential`` value when
  ``current_auth_method == "jwt"``, else empty string.
* ``${USER_API_KEY}`` → ``current_credential`` value when
  ``current_auth_method == "api_key"``, else empty string.

When the contextvars are unset (no auth context, e.g. tests), both
placeholders resolve to empty strings — enabling MCP credential propagation
to forward the current user's credential to remote MCP servers (raganything)
instead of a static env-var key.
"""

import os
import re
from typing import Any

# Reserved placeholders resolved from the RLS contextvars (NOT os.environ).
_USER_JWT = "USER_JWT"
_USER_API_KEY = "USER_API_KEY"
_USER_PLACEHOLDERS = frozenset({_USER_JWT, _USER_API_KEY})
_PLACEHOLDER_PATTERN = r"\$\{(\w+)\}"


def _resolve_user_placeholder(name: str) -> str:
    """Resolve a user-credential placeholder from the RLS contextvars.

    Args:
        name: The placeholder name (``USER_JWT`` or ``USER_API_KEY``).

    Returns:
        The raw credential when the auth method matches, otherwise an empty
        string. When the contextvars are unset, returns an empty string.
    """
    # Local import to avoid a circular dependency at module load time
    # (rls_context has no dependency on env_utils, but keep it local for clarity).
    from src.infrastructure.database.rls_context import current_auth_method, current_credential

    method = current_auth_method.get()
    cred = current_credential.get()
    if cred is None or method is None:
        return ""
    if name == _USER_JWT and method == "jwt":
        return cred
    if name == _USER_API_KEY and method == "api_key":
        return cred
    return ""


def resolve_env_vars(value: str) -> str:
    """Resolve ${VAR_NAME} patterns in a string using os.environ.

    If the variable is not set, the placeholder is kept as-is.

    Note: This does NOT resolve the user-credential placeholders
    (``${USER_JWT}`` / ``${USER_API_KEY}``). Use :func:`resolve_all_vars` for
    that.
    """
    return re.sub(
        _PLACEHOLDER_PATTERN,
        lambda m: os.environ.get(m.group(1), m.group(0)),
        value,
    )


def resolve_all_vars(value: str) -> str:
    """Resolve ${VAR_NAME} patterns using os.environ AND user-credential placeholders.

    Resolves both environment variables (``${OPENROUTER_API_KEY}`` etc.) and
    the reserved user-credential placeholders (``${USER_JWT}``,
    ``${USER_API_KEY}``) in a single pass. Unresolved os.environ placeholders
    are kept as-is; user-credential placeholders always resolve to a string
    (empty when the contextvars are unset or the method doesn't match).

    Args:
        value: The string potentially containing ``${VAR_NAME}`` placeholders.

    Returns:
        The string with all resolvable placeholders substituted.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in _USER_PLACEHOLDERS:
            return _resolve_user_placeholder(name)
        return os.environ.get(name, match.group(0))

    return re.sub(_PLACEHOLDER_PATTERN, _replace, value)


def resolve_env_vars_in_dict(mapping: dict[str, Any]) -> dict[str, Any]:
    """Resolve ${VAR_NAME} patterns in all string values of a dict.

    Non-string values are passed through unchanged. Uses
    :func:`resolve_all_vars` (os.environ + user-credential placeholders).
    """
    resolved: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, str):
            resolved[key] = resolve_all_vars(value)
        else:
            resolved[key] = value
    return resolved


def resolve_headers_drop_empty(mapping: dict[str, str]) -> dict[str, str]:
    """Resolve placeholders in HTTP headers and drop empty/credential-empty entries.

    Resolves both environment variables and user-credential placeholders
    (see :func:`resolve_all_vars`). A header entry is DROPPED when:

    * the resolved value is an empty string (e.g. ``X-API-Key: ""``), OR
    * the header contained a user-credential placeholder
      (``${USER_JWT}`` / ``${USER_API_KEY}``) that resolved to empty — this
      prevents sending a malformed ``Authorization: Bearer `` (with no token)
      to a remote MCP server.

    Non-string values are passed through unchanged. User placeholders are
    resolved exactly once per header value (the empty-resolution is tracked
    during the same pass that builds the resolved string).

    Args:
        mapping: The input header mapping (e.g. ``{"Authorization": "Bearer ${USER_JWT}"}``).

    Returns:
        A new dict with resolved values; entries dropped per the rules above.
    """
    resolved: dict[str, str] = {}
    for key, value in mapping.items():
        if not isinstance(value, str):
            resolved[key] = value
            continue

        user_placeholder_resolved_empty = False

        def _replace(match: re.Match[str]) -> str:
            nonlocal user_placeholder_resolved_empty
            name = match.group(1)
            if name in _USER_PLACEHOLDERS:
                rv = _resolve_user_placeholder(name)
                if rv == "":
                    user_placeholder_resolved_empty = True
                return rv
            return os.environ.get(name, match.group(0))

        rv = re.sub(r"\$\{(\w+)\}", _replace, value)
        if not rv or user_placeholder_resolved_empty:
            continue
        resolved[key] = rv
    return resolved
