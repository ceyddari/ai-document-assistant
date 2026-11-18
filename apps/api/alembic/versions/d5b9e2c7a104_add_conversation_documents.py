"""add conversation document scope

Revision ID: d5b9e2c7a104
Revises: c3e7a1f4d820
Create Date: 2026-11-18 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b9e2c7a104"
down_revision: str | Sequence[str] | None = "c3e7a1f4d820"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_documents",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id", "document_id"),
    )
    op.create_index(
        "ix_conversation_documents_document_id", "conversation_documents", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_documents_document_id", table_name="conversation_documents")
    op.drop_table("conversation_documents")
