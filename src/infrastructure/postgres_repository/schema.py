import logging

logger = logging.getLogger("composable-agents")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agent_configs (
    name VARCHAR(100) PRIMARY KEY,
    model VARCHAR(200) NOT NULL,
    minio_path VARCHAR(500) NOT NULL,
    is_builtin BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def ensure_schema(pool) -> None:
    """Create the agent_configs table if it does not exist.

    Args:
        pool: asyncpg connection pool.
    """
    await pool.execute(CREATE_TABLE_SQL)
    logger.info("Ensured agent_configs table exists")
