"""Migrate messages rows into trace_events.

Revision ID: 006
Revises: 005
Create Date: 2026-07-20

Mapping from legacy messages.role to trace_events.type:
  - human   -> human_message   (content kept as-is)
  - ai      -> ai_message      (content becomes JSON payload of the Message)
  - tool    -> tool_result     (content kept as-is, tool_calls -> metadata)
  - system  -> content         (content kept as-is)

Each legacy message gets a fresh turn_id (uuid) — the legacy schema did not
track turns. The AI message payload is reconstructed as the JSON serialization
of the relevant Message fields so that ``Message.from_trace_event`` can rebuild
the exact same entity.

Note: The legacy messages table did not have a tool_call_id column — tool_call
IDs were embedded in the tool_calls JSONB field. The migration preserves
tool_calls in the trace_events metadata, so no data is lost.

Downgrade limitation: the downgrade only backfills human_message and ai_message
rows. tool_result and content events are not reconstructed as legacy messages
on rollback. This is acceptable because the legacy messages table only had
human/ai/tool/system roles, and tool messages were ephemeral — losing them on
rollback does not affect conversation history.
"""

import json
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ROLE_TO_TYPE = {
    "human": "human_message",
    "ai": "ai_message",
    "tool": "tool_result",
    "system": "content",
}


def _fetch_messages(conn: Any) -> list[Any]:
    return list(
        conn.execute(
            text(
                "SELECT id, thread_id, role, content, timestamp, tool_calls, "
                "status, structured_response, thinking "
                "FROM messages ORDER BY thread_id, timestamp"
            )
        )
    )


def _build_event_row(row: Any) -> tuple[Any, ...]:
    role = row.role
    event_type = _ROLE_TO_TYPE.get(role, "content")
    turn_id = str(uuid4())
    content: str | None
    metadata: dict | None = None

    if event_type == "ai_message":
        payload: dict = {"content": row.content}
        if row.tool_calls is not None:
            payload["tool_calls"] = row.tool_calls
        if row.status is not None:
            payload["status"] = row.status
        if row.structured_response is not None:
            payload["structured_response"] = row.structured_response
        if row.thinking is not None:
            payload["thinking"] = row.thinking
        content = json.dumps(payload)
    elif event_type == "tool_result":
        content = row.content
        if row.tool_calls is not None:
            metadata = {"tool_calls": row.tool_calls}
        if row.status is not None:
            metadata = {**(metadata or {}), "status": row.status}
    else:
        content = row.content

    return (
        str(uuid4()),
        row.thread_id,
        turn_id,
        event_type,
        None,
        None,
        content,
        json.dumps(metadata) if metadata is not None else None,
        row.timestamp,
        0,
    )


def upgrade() -> None:
    conn = op.get_bind()
    rows = _fetch_messages(conn)
    if not rows:
        return

    values = [_build_event_row(row) for row in rows]
    conn.execute(
        text(
            "INSERT INTO trace_events "
            "(id, thread_id, turn_id, type, source, name, content, metadata, timestamp, sequence) "
            "VALUES (:id, :thread_id, :turn_id, :type, :source, :name, :content, :metadata, :timestamp, :sequence)"
        ),
        [
            {
                "id": v[0],
                "thread_id": v[1],
                "turn_id": v[2],
                "type": v[3],
                "source": v[4],
                "name": v[5],
                "content": v[6],
                "metadata": v[7],
                "timestamp": v[8],
                "sequence": v[9],
            }
            for v in values
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id VARCHAR(36) PRIMARY KEY, "
            "thread_id VARCHAR(36) NOT NULL REFERENCES threads(id) ON DELETE CASCADE, "
            "role VARCHAR(20) NOT NULL, "
            "content TEXT, "
            "timestamp TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "tool_calls JSONB, "
            "status VARCHAR(50), "
            "structured_response JSONB, "
            "thinking TEXT)"
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_messages_thread_id ON messages(thread_id);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_messages_thread_id_timestamp ON messages(thread_id, timestamp);"))

    rows = list(
        conn.execute(
            text(
                "SELECT id, thread_id, turn_id, type, content, metadata, timestamp "
                "FROM trace_events WHERE type IN ('human_message', 'ai_message') "
                "ORDER BY thread_id, timestamp"
            )
        )
    )

    type_to_role = {"human_message": "human", "ai_message": "ai"}
    values: list[dict] = []
    for row in rows:
        role = type_to_role[row.type]
        content: str | None = None
        tool_calls = None
        status = None
        structured_response = None
        thinking = None

        if row.type == "ai_message":
            payload = json.loads(row.content) if row.content else {}
            content = payload.get("content")
            tool_calls = payload.get("tool_calls")
            status = payload.get("status")
            structured_response = payload.get("structured_response")
            thinking = payload.get("thinking")
        else:
            content = row.content

        values.append(
            {
                "id": row.id,
                "thread_id": row.thread_id,
                "role": role,
                "content": content,
                "timestamp": row.timestamp,
                "tool_calls": json.dumps(tool_calls) if tool_calls is not None else None,
                "status": status,
                "structured_response": json.dumps(structured_response) if structured_response is not None else None,
                "thinking": thinking,
            }
        )

    if values:
        conn.execute(
            text(
                "INSERT INTO messages "
                "(id, thread_id, role, content, timestamp, tool_calls, status, structured_response, thinking) "
                "VALUES (:id, :thread_id, :role, :content, :timestamp, :tool_calls, :status, "
                ":structured_response, :thinking)"
            ),
            values,
        )
