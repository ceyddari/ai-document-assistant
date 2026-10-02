"""add deterministic message sequence

Revision ID: 9b0ef2b4183c
Revises: c84e12ab9f01
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9b0ef2b4183c"
down_revision: str | Sequence[str] | None = "c84e12ab9f01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("sequence", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH ordered_messages AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY conversation_id
                    ORDER BY
                        created_at,
                        CASE role WHEN 'user' THEN 0 ELSE 1 END,
                        id
                ) AS sequence
            FROM messages
        )
        UPDATE messages
        SET sequence = ordered_messages.sequence
        FROM ordered_messages
        WHERE messages.id = ordered_messages.id
        """
    )
    op.alter_column("messages", "sequence", existing_type=sa.Integer(), nullable=False)
    op.create_unique_constraint(
        "uq_messages_conversation_id_sequence",
        "messages",
        ["conversation_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_messages_conversation_id_sequence",
        "messages",
        type_="unique",
    )
    op.drop_column("messages", "sequence")
