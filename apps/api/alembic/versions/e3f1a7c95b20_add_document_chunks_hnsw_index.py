"""add HNSW index on document chunk embeddings

Revision ID: e3f1a7c95b20
Revises: 9b0ef2b4183c
Create Date: 2026-11-17 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3f1a7c95b20"
down_revision: str | Sequence[str] | None = "9b0ef2b4183c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Index embeddings for cosine search instead of scanning every chunk."""
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    # HNSW filters after the index scan; without iterative scan an organization with few
    # chunks among many can get fewer results than the limit (pgvector >= 0.8).
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'ALTER DATABASE %I SET hnsw.iterative_scan = strict_order', current_database()"
        "); END $$;"
    )


def downgrade() -> None:
    """Remove the embedding index."""
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'ALTER DATABASE %I RESET hnsw.iterative_scan', current_database()"
        "); END $$;"
    )
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
