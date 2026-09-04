from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page_number: int
    text: str


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
