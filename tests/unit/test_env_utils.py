"""Tests for environment variable utilities."""

from src.infrastructure.env_utils import resolve_env_vars, resolve_env_vars_in_dict


class TestResolveEnvVars:
    def test_resolves_single_var(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "sk-123")
        assert resolve_env_vars("${API_KEY}") == "sk-123"

    def test_resolves_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "8080")
        assert resolve_env_vars("http://${HOST}:${PORT}") == "http://localhost:8080"

    def test_preserves_missing_vars(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        assert resolve_env_vars("prefix-${MISSING_VAR}-suffix") == "prefix-${MISSING_VAR}-suffix"

    def test_does_not_touch_plain_strings(self):
        assert resolve_env_vars("plain-value") == "plain-value"

    def test_empty_string(self):
        assert resolve_env_vars("") == ""

    def test_mixed_existing_and_missing(self, monkeypatch):
        monkeypatch.setenv("FOUND", "yes")
        monkeypatch.delenv("GONE", raising=False)
        assert resolve_env_vars("${FOUND}-${GONE}") == "yes-${GONE}"


class TestResolveEnvVarsInDict:
    def test_resolves_string_values(self, monkeypatch):
        monkeypatch.setenv("TOKEN", "abc")
        result = resolve_env_vars_in_dict({"api_key": "${TOKEN}"})
        assert result == {"api_key": "abc"}

    def test_passes_through_int(self):
        result = resolve_env_vars_in_dict({"timeout": 30})
        assert result == {"timeout": 30}

    def test_passes_through_bool(self):
        result = resolve_env_vars_in_dict({"verbose": True})
        assert result == {"verbose": True}

    def test_passes_through_float(self):
        result = resolve_env_vars_in_dict({"temperature": 0.7})
        assert result == {"temperature": 0.7}

    def test_handles_empty_dict(self):
        assert resolve_env_vars_in_dict({}) == {}

    def test_mixed_types(self, monkeypatch):
        monkeypatch.setenv("KEY", "resolved")
        result = resolve_env_vars_in_dict(
            {
                "api_key": "${KEY}",
                "temperature": 0.5,
                "max_tokens": 1000,
                "stream": False,
            }
        )
        assert result == {
            "api_key": "resolved",
            "temperature": 0.5,
            "max_tokens": 1000,
            "stream": False,
        }
