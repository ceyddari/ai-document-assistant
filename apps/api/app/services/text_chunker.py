from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.pdf_parser import ParsedPage


@dataclass(frozen=True, slots=True)
class TextChunk:
    page_number: int
    chunk_index: int
    content: str


def chunk_pages(
    pages: list[ParsedPage],
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size sıfırdan büyük olmalıdır.")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap negatif olamaz.")

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap, chunk_size değerinden küçük olmalıdır.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",
            "\n",
            ". ",
            "? ",
            "! ",
            "; ",
            ", ",
            " ",
            "",
        ],
        length_function=len,
        is_separator_regex=False,
    )

    page_texts: list[str] = []
    page_metadata: list[dict[str, int]] = []

    for page in pages:
        if not page.text.strip():
            continue

        page_texts.append(page.text)
        page_metadata.append(
            {
                "page_number": page.page_number,
            }
        )

    langchain_documents = splitter.create_documents(
        page_texts,
        metadatas=page_metadata,
    )

    return [
        TextChunk(
            page_number=int(document.metadata["page_number"]),
            chunk_index=chunk_index,
            content=document.page_content,
        )
        for chunk_index, document in enumerate(langchain_documents)
    ]
