"""create folders and documents.folder_id

Revision ID: f5a2c8d41b73
Revises: e3f1a7c95b20
Create Date: 2026-11-17 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5a2c8d41b73"
down_revision: str | Sequence[str] | None = "e3f1a7c95b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_folders_organization_name"),
    )
    op.add_column("documents", sa.Column("folder_id", sa.Uuid(), nullable=True))
    op.create_index("ix_documents_folder_id", "documents", ["folder_id"])
    op.create_foreign_key(
        "fk_documents_folder_id", "documents", "folders", ["folder_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_documents_folder_id", "documents", type_="foreignkey")
    op.drop_index("ix_documents_folder_id", table_name="documents")
    op.drop_column("documents", "folder_id")
    op.drop_table("folders")
