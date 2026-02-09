import os
import re
from typing import Any


def resolve_env_vars(value: str) -> str:
    """Resolve ${VAR_NAME} patterns in a string using os.environ.

    If the variable is not set, the placeholder is kept as-is.
    """
    return re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), m.group(0)),
        value,
    )


def resolve_env_vars_in_dict(mapping: dict[str, Any]) -> dict[str, Any]:
    """Resolve ${VAR_NAME} patterns in all string values of a dict.

    Non-string values are passed through unchanged.
    """
    resolved: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, str):
            resolved[key] = resolve_env_vars(value)
        else:
            resolved[key] = value
    return resolved
