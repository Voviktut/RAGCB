from __future__ import annotations

import json
import os
from typing import Any
import urllib.error
import urllib.request

from app.rag import Chunk


OPENAI_API_URL = "https://api.openai.com/v1/responses"


def _build_context(results: list[tuple[Chunk, float]]) -> str:
    parts: list[str] = []
    for idx, (chunk, score) in enumerate(results, start=1):
        page = chunk.metadata.get("page", "—")
        section = chunk.metadata.get("section", "—")
        parts.append(f"[{idx}] {chunk.title} (score={score:.3f}, page={page}, section={section})\n{chunk.text}")
    return "\n\n".join(parts)


def _extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"].strip()

    output = payload.get("output", [])
    for item in output:
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = content.get("text", "").strip()
                if text:
                    return text
    return ""


class OpenAIAnswerGenerator:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-5")

    def enabled(self) -> bool:
        return bool(self.api_key)

    def generate(self, question: str, results: list[tuple[Chunk, float]]) -> str:
        context = _build_context(results)
        system = (
            "Ты корпоративный ассистент по внутренней документации. "
            "Отвечай только на основе предоставленного контекста. "
            "Если данных недостаточно — явно скажи об этом. "
            "Пиши как экспертное юридическое разъяснение: нейтрально, доказательно, без выдумывания норм. "
            "Обязательно приводи цитаты и указывай страницу/раздел из контекста."
        )
        user = (
            f"Вопрос сотрудника:\n{question}\n\n"
            f"Контекст из базы знаний:\n{context or 'Контекст пуст.'}\n\n"
            "Сформируй ответ в формате: 1) краткий итоговый тезис; 2) цитата(ы) из документа; 3) пояснение применимости; 4) блок 'Вывод'. "
            "Для каждого ключевого вывода добавляй ссылку вида [Источник N, стр. X, раздел Y]. "
            "Если в контексте нет прямого основания, явно укажи, что в этом документе соответствующие положения отсутствуют."
        )
        body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {"role": "user", "content": [{"type": "input_text", "text": user}]},
            ],
        }

        req = urllib.request.Request(
            OPENAI_API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI API unavailable: {exc}") from exc

        payload = json.loads(raw)
        text = _extract_output_text(payload)
        if not text:
            raise RuntimeError("OpenAI API returned empty response text")
        return text
