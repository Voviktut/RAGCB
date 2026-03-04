# Company RAG KB

RAG-система в виде веб-сайта для внутренней базы знаний компании.

## Что уже реализовано

- Веб-интерфейс с авторизацией и ролями:
  - `admin` — может загружать документы файлами (txt/md/docx/pdf) и задавать вопросы.
  - `user` — может только задавать вопросы.
- HTTP API + HTML-страницы в одном сервисе:
  - `GET /` — страница входа
  - `GET /app` — панель пользователя
  - `GET /health` — health-check
  - `POST /documents` — загрузка документа (JSON или multipart файл, только admin)
  - `POST /ask` — вопрос к базе знаний (авторизованные пользователи)
- RAG-ядро: чанкирование текста, retrieval по cosine similarity (Bag-of-Words), возврат источников.

## Быстрый старт

```bash
python app/main.py
# или
python -m app.main
```

После запуска рабочая ссылка:

- http://127.0.0.1:8000/

Тестовые пользователи:

- `admin / admin123`
- `employee / employee123`

## API-пример (admin)

```bash
curl -X POST http://127.0.0.1:8000/documents \
  -H 'Content-Type: application/json' \
  -H 'Cookie: session_id=<admin_session>' \
  -d '{
    "title":"Политика отпусков",
    "content":"Сотрудник оформляет отпуск через HR-систему за 14 дней до даты начала.",
    "metadata":{"owner":"HR"}
  }'
```


### Ответы через OpenAI API (последняя GPT)

По умолчанию сервис использует встроенный fallback-генератор.
Чтобы включить ответы через OpenAI API:

```bash
export OPENAI_API_KEY=<your_api_key>
export OPENAI_MODEL=gpt-5
python -m app.main
```

При наличии `OPENAI_API_KEY` endpoint `/ask` и веб-форма вопросов будут генерировать ответ через модель GPT по найденным источникам.
Если API недоступен, сервис автоматически переключится на локальный fallback-ответ.

## Что добавить следующим шагом

- Хранение документов и пользователей в БД.
- Интеграцию с SSO/LDAP.
- Подключение LLM и векторной БД.
- Загрузку PDF/DOCX/Confluence/Notion.


## Загрузка файла документа

Через сайт: в панели админа выберите файл (`.txt`, `.md`, `.docx`, `.pdf`) и загрузите его.

Через API (multipart/form-data):

```bash
curl -X POST http://127.0.0.1:8000/documents \
  -H "Cookie: session_id=<admin_session>" \
  -F "title=Регламент онбординга" \
  -F "document_file=@./onboarding.docx"
```


> Примечание: для `.docx` извлекается текст из `word/document.xml`; для `.pdf` используется базовый встроенный парсер текстовых операторов (`Tj`/`TJ`).
