import json
import os
from unittest.mock import patch

from app.llm import OpenAIAnswerGenerator
from app.rag import Chunk


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_openai_generator_disabled_without_key() -> None:
    with patch.dict(os.environ, {}, clear=True):
        gen = OpenAIAnswerGenerator()
        assert gen.enabled() is False


def test_openai_generator_parses_output_text() -> None:
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-5"}, clear=True):
        gen = OpenAIAnswerGenerator()
        fake_payload = {"output_text": "Готовый ответ"}
        chunk = Chunk(doc_id="1", title="Doc", text="Контент", metadata={})
        with patch("urllib.request.urlopen", return_value=_FakeResponse(fake_payload)):
            answer = gen.generate("Вопрос?", [(chunk, 0.9)])
        assert answer == "Готовый ответ"
