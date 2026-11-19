"""add document section summaries

Revision ID: e7d2b9c4a618
Revises: a9d3f6b2c715
Create Date: 2026-11-19 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7d2b9c4a618"
down_revision: str | Sequence[str] | None = "a9d3f6b2c715"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_section_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("first_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("level > 0", name="ck_document_section_summaries_level_positive"),
        sa.CheckConstraint(
            "start_page > 0 AND end_page >= start_page",
            name="ck_document_section_summaries_page_range",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["first_chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "level", "position", name="uq_document_section_summaries_position"
        ),
    )
    op.create_index(
        "ix_document_section_summaries_organization_id",
        "document_section_summaries",
        ["organization_id"],
    )
    op.create_index(
        "ix_document_section_summaries_document_id",
        "document_section_summaries",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_section_summaries_document_id", "document_section_summaries")
    op.drop_index("ix_document_section_summaries_organization_id", "document_section_summaries")
    op.drop_table("document_section_summaries")
