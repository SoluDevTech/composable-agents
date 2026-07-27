"""Tests for the FernetCrypto helper.

Pure unit tests (no I/O, no DB). The class does not exist yet, so these tests
fail at import until the green-phase implementation is added.
"""

import pytest
from cryptography.fernet import InvalidToken

from src.infrastructure.crypto.fernet_crypto import FernetCrypto

# A fixed Fernet key (generated once) used across these tests.
_TEST_KEY = "Yr5R5-6lRUaxEwZWVysIaFs5POHcLps2OZViwWAscaU="


class TestFernetCryptoRoundtrip:
    """encrypt / decrypt roundtrip preserves plaintext."""

    def test_roundtrip_simple(self):
        crypto = FernetCrypto(key=_TEST_KEY)
        token = crypto.encrypt("hello world")
        assert isinstance(token, str)
        assert crypto.decrypt(token) == "hello world"

    def test_roundtrip_api_key(self):
        crypto = FernetCrypto(key=_TEST_KEY)
        plaintext = "sk-test-123456789"
        token = crypto.encrypt(plaintext)
        assert token != plaintext  # actually encrypted
        assert crypto.decrypt(token) == plaintext

    def test_roundtrip_empty_string(self):
        crypto = FernetCrypto(key=_TEST_KEY)
        token = crypto.encrypt("")
        assert crypto.decrypt(token) == ""

    def test_different_plaintexts_yield_different_tokens(self):
        crypto = FernetCrypto(key=_TEST_KEY)
        t1 = crypto.encrypt("alpha")
        t2 = crypto.encrypt("beta")
        assert t1 != t2

    def test_same_plaintext_twice_yields_different_tokens(self):
        """Fernet embeds a random IV / timestamp so two encryptions differ."""
        crypto = FernetCrypto(key=_TEST_KEY)
        t1 = crypto.encrypt("same")
        t2 = crypto.encrypt("same")
        assert t1 != t2
        assert crypto.decrypt(t1) == crypto.decrypt(t2) == "same"


class TestFernetCryptoWrongToken:
    """decrypt raises InvalidToken on tampered / wrong-key tokens."""

    def test_decrypt_wrong_token_raises_invalid_token(self):
        crypto = FernetCrypto(key=_TEST_KEY)
        with pytest.raises(InvalidToken):
            crypto.decrypt("not-a-valid-fernet-token")

    def test_decrypt_token_from_other_key_raises(self):
        crypto1 = FernetCrypto(key=_TEST_KEY)
        other_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        crypto2 = FernetCrypto(key=other_key)
        token = crypto1.encrypt("secret")
        with pytest.raises(InvalidToken):
            crypto2.decrypt(token)


class TestFernetCryptoEmptyKey:
    """An empty key is invalid in production wiring (fail-fast)."""

    def test_empty_key_raises_value_error(self):
        with pytest.raises(ValueError):
            FernetCrypto(key="")

    def test_whitespace_only_key_raises_value_error(self):
        with pytest.raises(ValueError):
            FernetCrypto(key="   ")
