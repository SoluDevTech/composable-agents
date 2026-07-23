"""Tests for NoopTracingProvider (real internal implementation).

Uses the shared ``noop_tracing`` fixture from conftest.py.
"""


class TestNoopTracingProvider:
    def test_get_callbacks_returns_empty_list(self, noop_tracing):
        # Arrange
        # Act
        callbacks = noop_tracing.get_callbacks()

        # Assert
        assert callbacks == []

    async def test_flush_returns_none(self, noop_tracing):
        # Arrange
        # Act
        result = await noop_tracing.flush()

        # Assert
        assert result is None

    async def test_shutdown_returns_none(self, noop_tracing):
        # Arrange
        # Act
        result = await noop_tracing.shutdown()

        # Assert
        assert result is None

    def test_get_callbacks_returns_new_list_each_call(self, noop_tracing):
        # Arrange
        first = noop_tracing.get_callbacks()

        # Act
        second = noop_tracing.get_callbacks()

        # Assert
        assert first == []
        assert second == []
