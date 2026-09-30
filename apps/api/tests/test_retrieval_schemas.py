from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    RetrievedChunkResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)


def test_semantic_search_request_normalizes_query_and_uses_default_limit() -> None:
    request = SemanticSearchRequest(
        query="  Yıllık izin nasıl alınır?  ",
    )

    assert request.query == "Yıllık izin nasıl alınır?"
    assert request.limit == 5


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_semantic_search_request_rejects_blank_query(query: str) -> None:
    with pytest.raises(ValidationError):
        SemanticSearchRequest(query=query)


@pytest.mark.parametrize(
    "limit",
    [
        0,
        21,
    ],
)
def test_semantic_search_request_rejects_invalid_limit(limit: int) -> None:
    with pytest.raises(ValidationError):
        SemanticSearchRequest(
            query="Sürpriz Kasa projesinin mimarisi nedir?",
            limit=limit,
        )


def test_semantic_search_response_contains_source_information() -> None:
    chunk_id = uuid4()
    document_id = uuid4()

    response = SemanticSearchResponse(
        query="Sürpriz Kasa projesinin mimarisi nedir?",
        items=[
            RetrievedChunkResponse(
                chunk_id=chunk_id,
                document_id=document_id,
                filename="Surpriz_Kasa_Proje_Mimarisi.pdf",
                page_number=1,
                content="Proje mimarisi ve operasyonel akış.",
                similarity=0.6679,
            )
        ],
    )

    assert response.query == "Sürpriz Kasa projesinin mimarisi nedir?"
    assert len(response.items) == 1
    assert response.items[0].chunk_id == chunk_id
    assert response.items[0].document_id == document_id
    assert response.items[0].page_number == 1
    assert response.items[0].similarity == 0.6679
