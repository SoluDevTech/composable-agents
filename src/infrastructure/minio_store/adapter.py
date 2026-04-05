import io
import logging

from miniopy_async import Minio
from miniopy_async.error import S3Error

from src.domain.exceptions import AgentNotFoundError
from src.domain.ports.agent_config_store import AgentConfigStore

logger = logging.getLogger("composable-agents")


class MinioAgentConfigStore(AgentConfigStore):
    """Adapter that stores agent YAML configurations in MinIO (S3-compatible)."""

    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def put(self, path: str, yaml_content: str) -> None:
        """Upload YAML content for the given path."""
        data = yaml_content.encode("utf-8")
        stream = io.BytesIO(data)
        await self._client.put_object(
            self._bucket,
            path,
            stream,
            length=len(data),
            content_type="application/x-yaml",
        )
        logger.info("Uploaded agent config '%s' to MinIO bucket '%s'", path, self._bucket)

    async def get(self, path: str) -> str:
        """Download and return YAML content for the given path.

        Raises:
            AgentNotFoundError: If the object does not exist in MinIO.
        """
        try:
            response = await self._client.get_object(self._bucket, path)
            data = await response.read()
            response.close()
            await response.release()
            return data.decode("utf-8")
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise AgentNotFoundError(f"Agent config not found in store: {path}") from e
            raise

    async def delete(self, path: str) -> None:
        """Delete the YAML object for the given path.

        Raises:
            AgentNotFoundError: If the object does not exist in MinIO.
        """
        try:
            await self._client.remove_object(self._bucket, path)
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise AgentNotFoundError(f"Agent config not found in store: {path}") from e
            raise
        logger.info("Deleted agent config '%s' from MinIO bucket '%s'", path, self._bucket)

    async def exists(self, path: str) -> bool:
        """Check whether a YAML object exists for the given path."""
        try:
            await self._client.stat_object(self._bucket, path)
            return True
        except S3Error:
            return False

    async def ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist."""
        if await self._client.bucket_exists(self._bucket):
            logger.debug("MinIO bucket '%s' already exists", self._bucket)
            return
        await self._client.make_bucket(self._bucket)
        logger.info("Created MinIO bucket '%s'", self._bucket)
