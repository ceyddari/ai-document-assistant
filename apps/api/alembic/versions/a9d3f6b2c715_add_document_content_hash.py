"""add document content hash

Revision ID: a9d3f6b2c715
Revises: d5b9e2c7a104
Create Date: 2026-11-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9d3f6b2c715"
down_revision: str | Sequence[str] | None = "d5b9e2c7a104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable without backfill: existing rows keep working and are simply not matched as duplicates.
    op.add_column("documents", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.create_unique_constraint(
        "uq_documents_org_content_sha256", "documents", ["organization_id", "content_sha256"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_org_content_sha256", "documents", type_="unique")
    op.drop_column("documents", "content_sha256")
