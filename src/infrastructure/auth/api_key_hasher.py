"""Backward-compat re-export of :class:`ApiKeyHasher`.

The implementation now lives in :mod:`src.domain.services.auth.api_key_hasher`
(hash policy is domain logic). This thin re-export keeps existing imports
working; new code should import from the domain module directly.
"""

from src.domain.services.auth.api_key_hasher import ApiKeyHasher

__all__ = ["ApiKeyHasher"]
