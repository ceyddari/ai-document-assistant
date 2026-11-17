"""add chunk full-text search vector and message source position

Revision ID: b8c4d2e6f913
Revises: f5a2c8d41b73
Create Date: 2026-11-17 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c4d2e6f913"
down_revision: str | Sequence[str] | None = "f5a2c8d41b73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Generated column: existing chunks are backfilled by Postgres, new ones stay in sync.
    op.add_column(
        "document_chunks",
        sa.Column(
            "content_tsv",
            TSVECTOR(),
            sa.Computed("to_tsvector('turkish'::regconfig, content)", persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_document_chunks_content_tsv",
        "document_chunks",
        ["content_tsv"],
        postgresql_using="gin",
    )

    # Sources were shown in similarity order to match prompt numbering. With hybrid ranking
    # and citation filtering that no longer holds, so store the order explicitly.
    op.add_column("message_sources", sa.Column("position", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE message_sources AS source
        SET position = ranked.position
        FROM (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY message_id ORDER BY similarity DESC, id ASC
                ) - 1 AS position
            FROM message_sources
        ) AS ranked
        WHERE source.id = ranked.id
        """
    )
    op.alter_column("message_sources", "position", nullable=False)
    op.create_check_constraint(
        "ck_message_sources_position_non_negative",
        "message_sources",
        "position >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_message_sources_position_non_negative",
        "message_sources",
        type_="check",
    )
    op.drop_column("message_sources", "position")
    op.drop_index("ix_document_chunks_content_tsv", table_name="document_chunks")
    op.drop_column("document_chunks", "content_tsv")
