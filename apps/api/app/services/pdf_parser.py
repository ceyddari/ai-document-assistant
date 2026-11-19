from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class OutlineEntry:
    level: int
    title: str
    page_number: int | None


class PdfParsingError(Exception):
    pass


class EncryptedPdfError(PdfParsingError):
    pass


def parse_pdf(file_path: Path) -> list[ParsedPage]:
    try:
        reader = PdfReader(file_path)

        if reader.is_encrypted:
            raise EncryptedPdfError("Şifreli PDF dosyaları henüz desteklenmiyor.")

        pages: list[ParsedPage] = []

        for page_number, page in enumerate(reader.pages, start=1):
            extracted_text = page.extract_text() or ""
            normalized_text = extracted_text.replace("\x00", "").strip()

            pages.append(
                ParsedPage(
                    page_number=page_number,
                    text=normalized_text,
                )
            )

        return pages

    except EncryptedPdfError:
        raise

    except (OSError, PdfReadError, UnicodeError, ValueError) as error:
        raise PdfParsingError("PDF dosyası okunamadı.") from error


def parse_outline(file_path: Path, *, max_depth: int = 3) -> list[OutlineEntry]:
    """The PDF's bookmarks (its table of contents); [] when it has none or they are unreadable."""
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            return []
        entries: list[OutlineEntry] = []

        def walk(items: list, level: int) -> None:
            for item in items:
                # pypdf nests an entry's children as a list right after the entry.
                if isinstance(item, list):
                    if level < max_depth:
                        walk(item, level + 1)
                    continue
                title = " ".join(str(item.title or "").split())
                if not title:
                    continue
                page_index = reader.get_destination_page_number(item)
                page_number = page_index + 1 if page_index is not None and page_index >= 0 else None
                entries.append(OutlineEntry(level, title, page_number))

        walk(reader.outline, 1)
        return entries
    # Broken bookmarks in an uploaded file must not fail the question; callers fall back.
    except (
        OSError,
        PdfReadError,
        UnicodeError,
        ValueError,
        KeyError,
        IndexError,
        AttributeError,
        TypeError,
        RecursionError,
    ):
        return []
