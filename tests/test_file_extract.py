from io import BytesIO
from zipfile import ZipFile

from app.file_extract import extract_text_by_filename, extract_text_from_pdf


def _build_min_docx(text: str) -> bytes:
    xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>'''.encode("utf-8")
    bio = BytesIO()
    with ZipFile(bio, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return bio.getvalue()


def test_extract_docx_text() -> None:
    blob = _build_min_docx("Правило отпуска")
    text = extract_text_by_filename("policy.docx", blob)
    assert "Правило отпуска" in text


def test_extract_pdf_text() -> None:
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\nBT (Incident process) Tj ET\nendstream\nendobj\n%%EOF"
    text = extract_text_from_pdf(pdf)
    assert "Incident process" in text
