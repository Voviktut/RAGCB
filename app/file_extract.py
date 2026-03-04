from __future__ import annotations

from io import BytesIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.rag import Segment


HEADING_RE = re.compile(r"^(#+\s+.+|[А-ЯA-Z][А-ЯA-Z0-9\s\-]{6,})$")


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
    return "\n".join(seg.text for seg in extract_pdf_segments(file_bytes)).strip()


def extract_pdf_segments(file_bytes: bytes) -> list[Segment]:
    # Lightweight page split heuristic.
    pages = re.split(rb"/Type\s*/Page\b", file_bytes)
    segments: list[Segment] = []
    if len(pages) <= 1:
        pages = [file_bytes]
    else:
        pages = pages[1:]

    for i, page_blob in enumerate(pages, start=1):
        chunks = re.findall(rb"\((.*?)\)\s*Tj", page_blob, flags=re.DOTALL)
        chunks.extend(re.findall(rb"\[(.*?)\]\s*TJ", page_blob, flags=re.DOTALL))
        decoded: list[str] = []
        for ch in chunks:
            if b"(" in ch and b")" in ch:
                nested = re.findall(rb"\((.*?)\)", ch, flags=re.DOTALL)
                decoded.extend(_decode_pdf_escapes(x) for x in nested)
            else:
                decoded.append(_decode_pdf_escapes(ch))
        text = re.sub(r"\s+", " ", " ".join(decoded)).strip()
        if text:
            segments.append(Segment(text=text, page=i, section=None))
    return segments


def split_sections(text: str) -> list[Segment]:
    lines = [ln.strip() for ln in text.splitlines()]
    current_section = "Общий раздел"
    buff: list[str] = []
    segments: list[Segment] = []

    def flush() -> None:
        if buff:
            segments.append(Segment(text="\n".join(buff).strip(), section=current_section))
            buff.clear()

    for line in lines:
        if not line:
            continue
        if HEADING_RE.match(line):
            flush()
            current_section = line.lstrip("#").strip()
            continue
        buff.append(line)
    flush()
    return segments


def extract_segments_by_filename(filename: str, file_bytes: bytes) -> list[Segment]:
    lower = filename.lower()
    if lower.endswith(".txt") or lower.endswith(".md"):
        text = file_bytes.decode("utf-8", errors="ignore").strip()
        return split_sections(text)
    if lower.endswith(".docx"):
        return split_sections(extract_text_from_docx(file_bytes))
    if lower.endswith(".pdf"):
        return extract_pdf_segments(file_bytes)
    raise ValueError("unsupported file format")


def extract_text_by_filename(filename: str, file_bytes: bytes) -> str:
    return "\n".join(seg.text for seg in extract_segments_by_filename(filename, file_bytes)).strip()
