from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageSource(Base):
    __tablename__ = "message_sources"
    __table_args__ = (
        CheckConstraint(
            "similarity >= 0 AND similarity <= 1",
            name="ck_message_sources_similarity_range",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_message_sources_position_non_negative",
        ),
        UniqueConstraint(
            "message_id",
            "chunk_id",
            name="uq_message_sources_message_id_chunk_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    # 0-based order shown to the user; [Kaynak N] in the answer is position N - 1.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
