from pathlib import Path

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas

from app.services.pdf_parser import (
    EncryptedPdfError,
    PdfParsingError,
    parse_pdf,
)


def create_two_page_pdf(file_path: Path) -> None:
    canvas = Canvas(str(file_path))

    canvas.drawString(72, 720, "First page content")
    canvas.showPage()

    canvas.drawString(72, 720, "Second page content")
    canvas.save()


def create_blank_pdf(file_path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    with file_path.open("wb") as file:
        writer.write(file)


def create_encrypted_pdf(file_path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret-password")

    with file_path.open("wb") as file:
        writer.write(file)


def test_parse_pdf_extracts_text_from_each_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "two-pages.pdf"
    create_two_page_pdf(pdf_path)

    pages = parse_pdf(pdf_path)

    assert len(pages) == 2

    assert pages[0].page_number == 1
    assert "First page content" in pages[0].text

    assert pages[1].page_number == 2
    assert "Second page content" in pages[1].text


def test_parse_pdf_returns_empty_text_for_blank_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"
    create_blank_pdf(pdf_path)

    pages = parse_pdf(pdf_path)

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].text == ""


def test_parse_pdf_rejects_corrupted_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "corrupted.pdf"
    pdf_path.write_bytes(b"This is not a valid PDF file.")

    with pytest.raises(PdfParsingError, match="PDF dosyası okunamadı"):
        parse_pdf(pdf_path)


def test_parse_pdf_rejects_encrypted_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "encrypted.pdf"
    create_encrypted_pdf(pdf_path)

    with pytest.raises(
        EncryptedPdfError,
        match="Şifreli PDF dosyaları henüz desteklenmiyor",
    ):
        parse_pdf(pdf_path)
