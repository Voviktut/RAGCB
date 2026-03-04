from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import sqrt
from typing import Any
import re


WORD_RE = re.compile(r"[\w-]+", re.UNICODE)


@dataclass
class Chunk:
    doc_id: str
    title: str
    text: str
    metadata: dict[str, Any]


@dataclass
class Segment:
    text: str
    page: int | None = None
    section: str | None = None


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def cosine_bow(a: str, b: str) -> float:
    ca = Counter(tokenize(a))
    cb = Counter(tokenize(b))
    if not ca or not cb:
        return 0.0
    keys = set(ca) & set(cb)
    num = sum(ca[k] * cb[k] for k in keys)
    den_a = sqrt(sum(v * v for v in ca.values()))
    den_b = sqrt(sum(v * v for v in cb.values()))
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


class InMemoryKnowledgeBase:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    @property
    def chunks(self) -> list[Chunk]:
        return self._chunks

    def add_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        return self.add_segments(doc_id, title, [Segment(text=content)], metadata=metadata)

    def add_segments(
        self,
        doc_id: str,
        title: str,
        segments: list[Segment],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        metadata = metadata or {}
        created = 0
        for seg in segments:
            part_meta = dict(metadata)
            if seg.page is not None:
                part_meta["page"] = seg.page
            if seg.section:
                part_meta["section"] = seg.section
            for part in chunk_text(seg.text):
                self._chunks.append(Chunk(doc_id=doc_id, title=title, text=part, metadata=part_meta))
                created += 1
        return created

    def retrieve(self, question: str, top_k: int = 4) -> list[tuple[Chunk, float]]:
        ranked = [(chunk, cosine_bow(question, chunk.text)) for chunk in self._chunks]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return [(c, s) for c, s in ranked[:top_k] if s > 0]


class SimpleAnswerGenerator:
    @staticmethod
    def generate(question: str, results: list[tuple[Chunk, float]]) -> str:
        if not results:
            return "Я не нашёл релевантных данных. Загрузите документы и повторите запрос."

        lines = [f"Вопрос: {question}", "", "Ответ на основе внутренней документации:"]
        for idx, (chunk, score) in enumerate(results, start=1):
            quote = chunk.text[:240]
            page = chunk.metadata.get("page", "—")
            section = chunk.metadata.get("section", "—")
            lines.append(
                f"{idx}. Вывод по источнику [{chunk.title}] (релевантность {score:.2f}). "
                f"Цитата: «{quote}». Страница: {page}. Раздел: {section}."
            )
        lines.append("\nЕсли нужно, могу дать структурированный юридический разбор по пунктам.")
        return "\n".join(lines)
