"""Tests for MinioAgentConfigStore (MinIO adapter).

Mocks the miniopy-async Minio client at the external boundary (S3 API).
Imports all symbols at module top.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from miniopy_async.error import S3Error

from src.domain.errors.agent import AgentNotFoundError
from src.infrastructure.minio_store.adapter import MinioAgentConfigStore

BUCKET = "agent-configs"


def _s3_no_such_key() -> S3Error:
    return S3Error(
        code="NoSuchKey",
        message="The specified key does not exist.",
        resource="/agent-configs/nonexistent.yaml",
        request_id="test",
        host_id="test",
        response="test",
    )


class TestMinioAgentConfigStore:
    @pytest.fixture
    def mock_minio_client(self):
        client = AsyncMock()
        client.list_objects = MagicMock()
        return client

    @pytest.fixture
    def store(self, mock_minio_client):
        return MinioAgentConfigStore(client=mock_minio_client, bucket=BUCKET)

    async def test_put_uploads_yaml_content(self, store, mock_minio_client):
        # Arrange
        yaml_content = "name: my-agent\nmodel: gpt-4o"

        # Act
        await store.put("my-agent", yaml_content)

        # Assert
        mock_minio_client.put_object.assert_awaited_once()
        call_args = mock_minio_client.put_object.call_args
        assert call_args.args[0] == BUCKET

    async def test_get_returns_yaml_string(self, store, mock_minio_client):
        # Arrange
        response_mock = AsyncMock()
        response_mock.read.return_value = b"name: my-agent\nmodel: gpt-4o"
        response_mock.close = AsyncMock()
        response_mock.release = AsyncMock()
        mock_minio_client.get_object.return_value = response_mock

        # Act
        result = await store.get("my-agent")

        # Assert
        assert result == "name: my-agent\nmodel: gpt-4o"

    async def test_get_not_found_raises(self, store, mock_minio_client):
        # Arrange
        mock_minio_client.get_object.side_effect = _s3_no_such_key()

        # Act / Assert
        with pytest.raises(AgentNotFoundError):
            await store.get("nonexistent")

    async def test_delete_removes_object(self, store, mock_minio_client):
        # Arrange
        mock_minio_client.stat_object.return_value = MagicMock()

        # Act
        await store.delete("my-agent")

        # Assert
        mock_minio_client.remove_object.assert_awaited_once()

    async def test_delete_not_found_raises(self, store, mock_minio_client):
        # Arrange
        mock_minio_client.stat_object.side_effect = _s3_no_such_key()

        # Act / Assert
        with pytest.raises(AgentNotFoundError):
            await store.delete("nonexistent")

    async def test_exists_returns_true(self, store, mock_minio_client):
        # Arrange
        mock_minio_client.stat_object.return_value = MagicMock()

        # Act
        result = await store.exists("my-agent")

        # Assert
        assert result is True

    async def test_exists_returns_false(self, store, mock_minio_client):
        # Arrange
        mock_minio_client.stat_object.side_effect = _s3_no_such_key()

        # Act
        result = await store.exists("nonexistent")

        # Assert
        assert result is False

    async def test_list_all_returns_agent_names(self, store, mock_minio_client):
        # Arrange
        obj1 = MagicMock()
        obj1.object_name = "my-agent.yaml"
        obj1.is_dir = False
        obj2 = MagicMock()
        obj2.object_name = "coder.yaml"
        obj2.is_dir = False

        async def _async_iter():
            for item in [obj1, obj2]:
                yield item

        mock_minio_client.list_objects.return_value = _async_iter()

        # Act
        result = await store.list_all()

        # Assert
        assert sorted(result) == ["coder", "my-agent"]

    async def test_ensure_bucket_creates_if_missing(self, store, mock_minio_client):
        # Arrange
        mock_minio_client.bucket_exists.return_value = False

        # Act
        await store.ensure_bucket()

        # Assert
        mock_minio_client.make_bucket.assert_awaited_once_with(BUCKET)

    async def test_ensure_bucket_skips_if_exists(self, store, mock_minio_client):
        # Arrange
        mock_minio_client.bucket_exists.return_value = True

        # Act
        await store.ensure_bucket()

        # Assert
        mock_minio_client.make_bucket.assert_not_awaited()
