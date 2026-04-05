import logging

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.exceptions import AgentNotFoundError
from src.domain.ports.agent_config_repository import AgentConfigRepository

logger = logging.getLogger("composable-agents")

UPSERT_SQL = """
INSERT INTO agent_configs (name, model, minio_path, is_builtin, created_at, updated_at)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (name) DO UPDATE SET
    model = EXCLUDED.model,
    minio_path = EXCLUDED.minio_path,
    is_builtin = EXCLUDED.is_builtin,
    updated_at = EXCLUDED.updated_at;
"""

SELECT_ONE_SQL = "SELECT name, model, minio_path, is_builtin, created_at, updated_at FROM agent_configs WHERE name = $1"
SELECT_ALL_SQL = "SELECT name, model, minio_path, is_builtin, created_at, updated_at FROM agent_configs ORDER BY name"
DELETE_SQL = "DELETE FROM agent_configs WHERE name = $1"
EXISTS_SQL = "SELECT EXISTS(SELECT 1 FROM agent_configs WHERE name = $1)"


class PostgresAgentConfigRepository(AgentConfigRepository):
    """Adapter that persists agent configuration metadata in PostgreSQL via asyncpg."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def save(self, metadata: AgentConfigMetadata) -> None:
        """Insert or update agent configuration metadata."""
        await self._pool.execute(
            UPSERT_SQL,
            metadata.name,
            metadata.model,
            metadata.minio_path,
            metadata.is_builtin,
            metadata.created_at,
            metadata.updated_at,
        )
        logger.info("Saved agent config metadata '%s'", metadata.name)

    async def get(self, name: str) -> AgentConfigMetadata:
        """Retrieve metadata by agent name.

        Raises:
            AgentNotFoundError: If no row exists for this name.
        """
        row = await self._pool.fetchrow(SELECT_ONE_SQL, name)
        if row is None:
            raise AgentNotFoundError(f"Agent config metadata not found: {name}")
        return AgentConfigMetadata(**dict(row))

    async def list_all(self) -> list[AgentConfigMetadata]:
        """List all agent configuration metadata."""
        rows = await self._pool.fetch(SELECT_ALL_SQL)
        return [AgentConfigMetadata(**dict(row)) for row in rows]

    async def delete(self, name: str) -> None:
        """Delete metadata by agent name.

        Raises:
            AgentNotFoundError: If no row was deleted.
        """
        result = await self._pool.execute(DELETE_SQL, name)
        if result == "DELETE 0":
            raise AgentNotFoundError(f"Agent config metadata not found: {name}")
        logger.info("Deleted agent config metadata '%s'", name)

    async def exists(self, name: str) -> bool:
        """Check whether metadata exists for the given agent name."""
        return await self._pool.fetchval(EXISTS_SQL, name)
