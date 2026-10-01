from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models import Conversation, Message, MessageRole, MessageSource


def test_conversation_model_has_tenant_and_timestamps() -> None:
    table = Conversation.__table__

    assert table.name == "conversations"
    assert table.c.organization_id.nullable is False
    assert table.c.organization_id.index is True
    assert table.c.title.nullable is True
    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None


def test_message_model_supports_only_user_and_assistant_roles() -> None:
    table = Message.__table__

    assert table.name == "messages"
    assert table.c.organization_id.nullable is False
    assert table.c.conversation_id.nullable is False
    assert table.c.content.nullable is False
    assert set(table.c.role.type.enums) == {
        MessageRole.USER.value,
        MessageRole.ASSISTANT.value,
    }


def test_message_source_model_preserves_chunk_and_similarity() -> None:
    table = MessageSource.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert table.name == "message_sources"
    assert table.c.organization_id.nullable is False
    assert table.c.message_id.nullable is False
    assert table.c.chunk_id.nullable is False
    assert table.c.similarity.nullable is False
    assert "ck_message_sources_similarity_range" in constraint_names
    assert "uq_message_sources_message_id_chunk_id" in constraint_names
    assert any(isinstance(item, CheckConstraint) for item in table.constraints)
    assert any(isinstance(item, UniqueConstraint) for item in table.constraints)


def test_conversation_foreign_keys_cascade() -> None:
    conversation_foreign_key = next(iter(Conversation.__table__.c.organization_id.foreign_keys))
    message_foreign_keys = {
        foreign_key.target_fullname: foreign_key.ondelete
        for column in (Message.__table__.c.organization_id, Message.__table__.c.conversation_id)
        for foreign_key in column.foreign_keys
    }
    source_foreign_keys = {
        foreign_key.target_fullname: foreign_key.ondelete
        for column in (
            MessageSource.__table__.c.organization_id,
            MessageSource.__table__.c.message_id,
            MessageSource.__table__.c.chunk_id,
        )
        for foreign_key in column.foreign_keys
    }

    assert conversation_foreign_key.ondelete == "CASCADE"
    assert message_foreign_keys == {
        "organizations.id": "CASCADE",
        "conversations.id": "CASCADE",
    }
    assert source_foreign_keys == {
        "organizations.id": "CASCADE",
        "messages.id": "CASCADE",
        "document_chunks.id": "CASCADE",
    }
