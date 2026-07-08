"""Tests for environment variable utilities."""

from src.infrastructure.env_utils import resolve_env_vars, resolve_env_vars_in_dict


class TestResolveEnvVars:
    """Tests for resolve_env_vars."""

    def test_resolves_single_var(self, monkeypatch):
        """Should substitute a single env var reference."""
        # Arrange
        monkeypatch.setenv("API_KEY", "sk-123")

        # Act
        result = resolve_env_vars("${API_KEY}")

        # Assert
        assert result == "sk-123"

    def test_resolves_multiple_vars(self, monkeypatch):
        """Should substitute multiple env var references in one string."""
        # Arrange
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "8080")

        # Act
        result = resolve_env_vars("http://${HOST}:${PORT}")

        # Assert
        assert result == "http://localhost:8080"

    def test_preserves_missing_vars(self, monkeypatch):
        """Should leave unresolved references intact."""
        # Arrange
        monkeypatch.delenv("MISSING_VAR", raising=False)

        # Act
        result = resolve_env_vars("prefix-${MISSING_VAR}-suffix")

        # Assert
        assert result == "prefix-${MISSING_VAR}-suffix"

    def test_does_not_touch_plain_strings(self):
        """Should return plain strings unchanged."""
        # Arrange
        # Act
        result = resolve_env_vars("plain-value")

        # Assert
        assert result == "plain-value"

    def test_empty_string_returns_empty(self):
        """Should return empty string for empty input."""
        # Arrange
        # Act
        result = resolve_env_vars("")

        # Assert
        assert result == ""

    def test_mixed_existing_and_missing(self, monkeypatch):
        """Should resolve existing vars and preserve missing ones."""
        # Arrange
        monkeypatch.setenv("FOUND", "yes")
        monkeypatch.delenv("GONE", raising=False)

        # Act
        result = resolve_env_vars("${FOUND}-${GONE}")

        # Assert
        assert result == "yes-${GONE}"


class TestResolveEnvVarsInDict:
    """Tests for resolve_env_vars_in_dict."""

    def test_resolves_string_values(self, monkeypatch):
        """Should resolve env vars in string values."""
        # Arrange
        monkeypatch.setenv("TOKEN", "abc")

        # Act
        result = resolve_env_vars_in_dict({"api_key": "${TOKEN}"})

        # Assert
        assert result == {"api_key": "abc"}

    def test_passes_through_int(self):
        """Should pass int values through unchanged."""
        # Arrange
        # Act
        result = resolve_env_vars_in_dict({"timeout": 30})

        # Assert
        assert result == {"timeout": 30}

    def test_passes_through_bool(self):
        """Should pass bool values through unchanged."""
        # Arrange
        # Act
        result = resolve_env_vars_in_dict({"verbose": True})

        # Assert
        assert result == {"verbose": True}

    def test_passes_through_float(self):
        """Should pass float values through unchanged."""
        # Arrange
        # Act
        result = resolve_env_vars_in_dict({"temperature": 0.7})

        # Assert
        assert result == {"temperature": 0.7}

    def test_handles_empty_dict(self):
        """Should return an empty dict for an empty dict input."""
        # Arrange
        # Act
        result = resolve_env_vars_in_dict({})

        # Assert
        assert result == {}

    def test_mixed_types(self, monkeypatch):
        """Should resolve strings and pass through other types."""
        # Arrange
        monkeypatch.setenv("KEY", "resolved")

        # Act
        result = resolve_env_vars_in_dict(
            {
                "api_key": "${KEY}",
                "temperature": 0.5,
                "max_tokens": 1000,
                "stream": False,
            }
        )

        # Assert
        assert result == {
            "api_key": "resolved",
            "temperature": 0.5,
            "max_tokens": 1000,
            "stream": False,
        }
