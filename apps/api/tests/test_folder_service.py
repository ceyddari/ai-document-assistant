from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import Folder
from app.services.folder_service import resolve_folder_mentions


def _session_with(folders: list[Folder]) -> AsyncMock:
    session = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = folders
    session.scalars.return_value = scalars
    return session


@pytest.mark.asyncio
async def test_resolve_folder_mentions_prefers_longest_name_and_strips_mentions() -> None:
    short = Folder(id=uuid4(), organization_id=uuid4(), name="Finans")
    long = Folder(id=uuid4(), organization_id=short.organization_id, name="Finans Raporları")
    session = _session_with([short, long])

    ids, text = await resolve_folder_mentions(
        organization_id=short.organization_id,
        text="@finans raporları içinde bütçe nedir? info@finans.com",
        session=session,
    )

    assert ids == [long.id]
    assert text == "içinde bütçe nedir? info@finans.com"


@pytest.mark.asyncio
async def test_resolve_folder_mentions_without_mention_returns_text_unchanged() -> None:
    folder = Folder(id=uuid4(), organization_id=uuid4(), name="İK")
    ids, text = await resolve_folder_mentions(
        organization_id=folder.organization_id, text="İzin kaç gün?", session=_session_with([folder])
    )
    assert ids == []
    assert text == "İzin kaç gün?"
