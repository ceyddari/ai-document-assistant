"""add message feedback

Revision ID: c3e7a1f4d820
Revises: b8c4d2e6f913
Create Date: 2026-11-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e7a1f4d820"
down_revision: str | Sequence[str] | None = "b8c4d2e6f913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable without default: code that does not know the column keeps working.
    op.add_column("messages", sa.Column("feedback", sa.SmallInteger(), nullable=True))
    op.create_check_constraint("ck_messages_feedback_vote", "messages", "feedback IN (-1, 1)")


def downgrade() -> None:
    op.drop_constraint("ck_messages_feedback_vote", "messages", type_="check")
    op.drop_column("messages", "feedback")
