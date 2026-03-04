from app.rag import InMemoryKnowledgeBase, chunk_text


def test_chunk_text_splits_long_text() -> None:
    text = "A" * 1900
    chunks = chunk_text(text, chunk_size=800, overlap=100)
    assert len(chunks) == 3
    assert len(chunks[0]) == 800


def test_retrieve_returns_relevant_chunk() -> None:
    kb = InMemoryKnowledgeBase()
    kb.add_document(
        doc_id="doc-1",
        title="Политика отпусков",
        content="Сотрудник оформляет отпуск через HR-систему за 14 дней до даты начала.",
    )
    kb.add_document(
        doc_id="doc-2",
        title="Инциденты",
        content="При критическом инциденте нужно открыть тикет в течение 15 минут.",
    )

    results = kb.retrieve("Как оформить отпуск?", top_k=1)
    assert len(results) == 1
    assert results[0][0].title == "Политика отпусков"
