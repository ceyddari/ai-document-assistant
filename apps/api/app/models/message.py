from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_messages_conversation_id_sequence",
        ),
        CheckConstraint("feedback IN (-1, 1)", name="ck_messages_feedback_vote"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            name="message_role",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    # User vote on an assistant answer: 1 helpful, -1 not helpful, NULL no vote.
    feedback: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
