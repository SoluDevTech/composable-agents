"""Shared pytest fixtures for the composable-agents test suite.

Uses real internal implementations (InMemoryThreadRepository for test, YamlAgentConfigLoader,
NoopTracingProvider). External adapters are provided by tests/fixtures/external.py.
"""

import pytest

from src.infrastructure.tracing.noop_adapter import NoopTracingProvider
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader
from tests.fixtures.in_memory_thread_repository import InMemoryThreadRepository

# Re-export external fixtures so they are available to all tests
pytest_plugins = ["tests.fixtures.external"]


@pytest.fixture
def thread_repo():
    """Provide a real InMemoryThreadRepository for each test."""
    return InMemoryThreadRepository()


@pytest.fixture
def yaml_loader():
    """Provide a real YamlAgentConfigLoader for each test."""
    return YamlAgentConfigLoader()


@pytest.fixture
def noop_tracing():
    """Provide a real NoopTracingProvider for each test."""
    return NoopTracingProvider()
