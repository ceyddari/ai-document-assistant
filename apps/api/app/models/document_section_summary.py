from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentSectionSummary(Base):
    """A summary of consecutive pages; level 1 summarizes chunks, level N+1 summarizes level N.

    A document's levels are written in one transaction, so any row means its set is complete.
    """

    __tablename__ = "document_section_summaries"
    __table_args__ = (
        CheckConstraint("level > 0", name="ck_document_section_summaries_level_positive"),
        CheckConstraint(
            "start_page > 0 AND end_page >= start_page",
            name="ck_document_section_summaries_page_range",
        ),
        UniqueConstraint(
            "document_id", "level", "position", name="uq_document_section_summaries_position"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Citations are stored per chunk (message_sources.chunk_id), so a section cites its first one.
    first_chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
