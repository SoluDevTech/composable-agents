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

    def _key(self, name: str) -> str:
        return f"{name}.yaml"

    async def put(self, name: str, yaml_content: str) -> None:
        """Upload YAML content for the given agent name."""
        data = yaml_content.encode("utf-8")
        stream = io.BytesIO(data)
        await self._client.put_object(
            self._bucket,
            self._key(name),
            stream,
            length=len(data),
            content_type="application/x-yaml",
        )
        logger.info("Uploaded agent config '%s' to MinIO bucket '%s'", name, self._bucket)

    async def get(self, name: str) -> str:
        """Download and return YAML content for the given agent name.

        Raises:
            AgentNotFoundError: If the object does not exist in MinIO.
        """
        try:
            response = await self._client.get_object(self._bucket, self._key(name))
            data = await response.read()
            response.close()
            await response.release()
            return data.decode("utf-8")
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise AgentNotFoundError(f"Agent config not found in store: {name}") from e
            raise

    async def delete(self, name: str) -> None:
        """Delete the YAML object for the given agent name.

        Raises:
            AgentNotFoundError: If the object does not exist in MinIO.
        """
        try:
            await self._client.stat_object(self._bucket, self._key(name))
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise AgentNotFoundError(f"Agent config not found in store: {name}") from e
            raise
        await self._client.remove_object(self._bucket, self._key(name))
        logger.info("Deleted agent config '%s' from MinIO bucket '%s'", name, self._bucket)

    async def exists(self, name: str) -> bool:
        """Check whether a YAML object exists for the given agent name."""
        try:
            await self._client.stat_object(self._bucket, self._key(name))
            return True
        except S3Error:
            return False

    async def list_all(self) -> list[str]:
        """List all agent names stored in the bucket."""
        return [
            obj.object_name.removesuffix(".yaml")
            async for obj in self._client.list_objects(self._bucket)
            if not obj.is_dir
        ]

    async def ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist."""
        if await self._client.bucket_exists(self._bucket):
            logger.debug("MinIO bucket '%s' already exists", self._bucket)
            return
        await self._client.make_bucket(self._bucket)
        logger.info("Created MinIO bucket '%s'", self._bucket)
