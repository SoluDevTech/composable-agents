"""Drop legacy messages table.

Revision ID: 007
Revises: 006
Create Date: 2026-07-20

The ``messages`` table is replaced by ``trace_events`` as the single source of
truth. The downgrade rebuilds it from the HUMAN_MESSAGE + AI_MESSAGE events
(see revision 006's downgrade for the actual data backfill).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_thread_id_timestamp;")
    op.execute("DROP INDEX IF EXISTS ix_messages_thread_id;")
    op.execute("DROP TABLE IF EXISTS messages;")


def downgrade() -> None:
    # The schema is recreated by revision 006's downgrade, which runs before
    # this one when walking down. Nothing to do here except ensure the table
    # exists (idempotent) — the data backfill is handled in 006.
    pass
