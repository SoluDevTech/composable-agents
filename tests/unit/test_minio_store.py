"""Tests for MinioAgentConfigStore (MinIO adapter).

Mocks the miniopy-async Minio client at the external boundary.
Tests verify that the adapter correctly translates domain operations
into MinIO S3 API calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.exceptions import AgentNotFoundError
from src.infrastructure.minio_store.adapter import MinioAgentConfigStore

BUCKET = "agent-configs"


class TestMinioAgentConfigStore:
    @pytest.fixture
    def mock_minio_client(self):
        """AsyncMock for the miniopy-async Minio client."""
        client = AsyncMock()
        # list_objects is sync in miniopy-async (returns async iterator), so use MagicMock
        client.list_objects = MagicMock()
        return client

    @pytest.fixture
    def store(self, mock_minio_client):
        """MinioAgentConfigStore wired to a mocked Minio client."""
        return MinioAgentConfigStore(client=mock_minio_client, bucket=BUCKET)

    # -- put ---------------------------------------------------------------

    async def test_put_uploads_yaml_content(self, store, mock_minio_client):
        """put should call put_object with correct bucket, key, and content."""
        await store.put("my-agent", "name: my-agent\nmodel: gpt-4o")

        mock_minio_client.put_object.assert_awaited_once()
        call_kwargs = mock_minio_client.put_object.call_args
        assert call_kwargs[0][0] == BUCKET or call_kwargs.kwargs.get("bucket_name") == BUCKET

    # -- get ---------------------------------------------------------------

    async def test_get_returns_yaml_string(self, store, mock_minio_client):
        """get should fetch the object and return decoded YAML content."""
        response_mock = AsyncMock()
        response_mock.read.return_value = b"name: my-agent\nmodel: gpt-4o"
        response_mock.close = AsyncMock()
        response_mock.release = AsyncMock()
        mock_minio_client.get_object.return_value = response_mock

        result = await store.get("my-agent")

        assert result == "name: my-agent\nmodel: gpt-4o"
        mock_minio_client.get_object.assert_awaited_once()

    async def test_get_not_found_raises(self, store, mock_minio_client):
        """get should raise AgentNotFoundError when the object does not exist."""
        from miniopy_async.error import S3Error

        error = S3Error(
            code="NoSuchKey",
            message="The specified key does not exist.",
            resource="/agent-configs/nonexistent.yaml",
            request_id="test",
            host_id="test",
            response="test",
        )
        mock_minio_client.get_object.side_effect = error

        with pytest.raises(AgentNotFoundError):
            await store.get("nonexistent")

    # -- delete ------------------------------------------------------------

    async def test_delete_removes_object(self, store, mock_minio_client):
        """delete should call remove_object with correct bucket and key."""
        mock_minio_client.stat_object.return_value = MagicMock()

        await store.delete("my-agent")

        mock_minio_client.remove_object.assert_awaited_once()

    async def test_delete_not_found_raises(self, store, mock_minio_client):
        """delete should raise AgentNotFoundError when object does not exist."""
        from miniopy_async.error import S3Error

        error = S3Error(
            code="NoSuchKey",
            message="The specified key does not exist.",
            resource="/agent-configs/nonexistent.yaml",
            request_id="test",
            host_id="test",
            response="test",
        )
        mock_minio_client.stat_object.side_effect = error

        with pytest.raises(AgentNotFoundError):
            await store.delete("nonexistent")

    # -- exists ------------------------------------------------------------

    async def test_exists_returns_true(self, store, mock_minio_client):
        """exists should return True when stat_object succeeds."""
        mock_minio_client.stat_object.return_value = MagicMock()

        result = await store.exists("my-agent")

        assert result is True
        mock_minio_client.stat_object.assert_awaited_once()

    async def test_exists_returns_false(self, store, mock_minio_client):
        """exists should return False when stat_object raises S3Error."""
        from miniopy_async.error import S3Error

        error = S3Error(
            code="NoSuchKey",
            message="The specified key does not exist.",
            resource="/agent-configs/nonexistent.yaml",
            request_id="test",
            host_id="test",
            response="test",
        )
        mock_minio_client.stat_object.side_effect = error

        result = await store.exists("nonexistent")

        assert result is False

    # -- list_all ----------------------------------------------------------

    async def test_list_all_returns_agent_names(self, store, mock_minio_client):
        """list_all should parse object names and return agent names."""
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

        result = await store.list_all()

        assert sorted(result) == ["coder", "my-agent"]

    # -- ensure_bucket -----------------------------------------------------

    async def test_ensure_bucket_creates_if_missing(self, store, mock_minio_client):
        """ensure_bucket should call make_bucket when bucket does not exist."""
        mock_minio_client.bucket_exists.return_value = False

        await store.ensure_bucket()

        mock_minio_client.make_bucket.assert_awaited_once_with(BUCKET)

    async def test_ensure_bucket_skips_if_exists(self, store, mock_minio_client):
        """ensure_bucket should not create bucket when it already exists."""
        mock_minio_client.bucket_exists.return_value = True

        await store.ensure_bucket()

        mock_minio_client.make_bucket.assert_not_awaited()
