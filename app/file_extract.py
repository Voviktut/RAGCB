from __future__ import annotations

from io import BytesIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile


def extract_text_from_docx(file_bytes: bytes) -> str:
    with ZipFile(BytesIO(file_bytes)) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts = [node.text for node in root.findall(".//w:t", ns) if node.text]
    return "\n".join(parts).strip()


def _decode_pdf_escapes(raw: bytes) -> str:
    text = raw.decode("latin1", errors="ignore")
    text = text.replace(r"\n", "\n").replace(r"\r", "\n").replace(r"\t", " ")
    text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return text


def extract_text_from_pdf(file_bytes: bytes) -> str:
    chunks = re.findall(rb"\((.*?)\)\s*Tj", file_bytes, flags=re.DOTALL)
    chunks.extend(re.findall(rb"\[(.*?)\]\s*TJ", file_bytes, flags=re.DOTALL))
    decoded: list[str] = []
    for ch in chunks:
        if b"(" in ch and b")" in ch:
            nested = re.findall(rb"\((.*?)\)", ch, flags=re.DOTALL)
            decoded.extend(_decode_pdf_escapes(x) for x in nested)
        else:
            decoded.append(_decode_pdf_escapes(ch))
    text = " ".join(decoded)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_text_by_filename(filename: str, file_bytes: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".txt") or lower.endswith(".md"):
        return file_bytes.decode("utf-8", errors="ignore").strip()
    if lower.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    if lower.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    raise ValueError("unsupported file format")
