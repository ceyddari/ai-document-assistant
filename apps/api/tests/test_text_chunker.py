import pytest

from app.services import ParsedPage, TextChunk, chunk_pages


def test_chunk_pages_returns_single_chunk_for_short_text() -> None:
    pages = [
        ParsedPage(
            page_number=1,
            text="Yıllık izin talebi sistem üzerinden oluşturulur.",
        )
    ]

    chunks = chunk_pages(
        pages,
        chunk_size=100,
        chunk_overlap=20,
    )

    assert chunks == [
        TextChunk(
            page_number=1,
            chunk_index=0,
            content="Yıllık izin talebi sistem üzerinden oluşturulur.",
        )
    ]


def test_chunk_pages_creates_overlap_between_chunks() -> None:
    pages = [
        ParsedPage(
            page_number=1,
            text="abcdefghij",
        )
    ]

    chunks = chunk_pages(
        pages,
        chunk_size=6,
        chunk_overlap=2,
    )

    assert chunks == [
        TextChunk(
            page_number=1,
            chunk_index=0,
            content="abcdef",
        ),
        TextChunk(
            page_number=1,
            chunk_index=1,
            content="efghij",
        ),
    ]


def test_chunk_pages_preserves_page_numbers_and_skips_blank_pages() -> None:
    pages = [
        ParsedPage(
            page_number=1,
            text="   ",
        ),
        ParsedPage(
            page_number=2,
            text="Yıllık izin prosedürü.",
        ),
        ParsedPage(
            page_number=3,
            text="Satın alma prosedürü.",
        ),
    ]

    chunks = chunk_pages(
        pages,
        chunk_size=100,
        chunk_overlap=20,
    )

    assert [chunk.page_number for chunk in chunks] == [2, 3]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.content for chunk in chunks] == [
        "Yıllık izin prosedürü.",
        "Satın alma prosedürü.",
    ]


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap", "error_message"),
    [
        (0, 0, "chunk_size sıfırdan büyük olmalıdır"),
        (100, -1, "chunk_overlap negatif olamaz"),
        (
            100,
            100,
            "chunk_overlap, chunk_size değerinden küçük olmalıdır",
        ),
    ],
)
def test_chunk_pages_rejects_invalid_settings(
    chunk_size: int,
    chunk_overlap: int,
    error_message: str,
) -> None:
    pages = [
        ParsedPage(
            page_number=1,
            text="Test content",
        )
    ]

    with pytest.raises(ValueError, match=error_message):
        chunk_pages(
            pages,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
