from __future__ import annotations

import json
import os
import re
import sys
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
from urllib.parse import parse_qs, urlparse
import uuid

if __package__ in (None, ""):
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.rag import InMemoryKnowledgeBase, SimpleAnswerGenerator


kb = InMemoryKnowledgeBase()

USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "employee": {"password": "employee123", "role": "user"},
}
SESSIONS: dict[str, dict[str, str]] = {}


MULTIPART_BOUNDARY_RE = re.compile(r"boundary=([^;]+)")


def render_html(title: str, body: str) -> bytes:
    html = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; background: #f5f7fb; margin: 0; }}
    .container {{ max-width: 920px; margin: 30px auto; background: #fff; padding: 24px; border-radius: 12px; box-shadow: 0 5px 20px rgba(0,0,0,.08); }}
    h1,h2 {{ margin-top: 0; }}
    .muted {{ color: #666; font-size: 14px; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 14px; margin-bottom: 14px; }}
    input, textarea, button, select {{ width: 100%; padding: 10px; margin: 6px 0 12px; border-radius: 8px; border: 1px solid #c9c9c9; box-sizing: border-box; }}
    button {{ background: #1d4ed8; color: #fff; border: none; cursor: pointer; font-weight: 600; }}
    button:hover {{ background: #1e40af; }}
    .alert {{ padding: 10px; border-radius: 8px; margin-bottom: 12px; background: #eef2ff; }}
    pre {{ background: #0f172a; color: #f8fafc; padding: 12px; border-radius: 8px; overflow: auto; white-space: pre-wrap; }}
    .tag {{ display: inline-block; background: #e2e8f0; padding: 4px 8px; border-radius: 999px; font-size: 12px; }}
    .sources li {{ margin-bottom: 8px; }}
  </style>
</head>
<body>
  <div class="container">
    {body}
  </div>
</body>
</html>"""
    return html.encode("utf-8")


def _parse_multipart_form_data(content_type: str, body: bytes) -> dict[str, tuple[str | None, bytes]]:
    match = MULTIPART_BOUNDARY_RE.search(content_type)
    if not match:
        return {}

    boundary = match.group(1).strip().strip('"').encode("utf-8")
    delimiter = b"--" + boundary
    result: dict[str, tuple[str | None, bytes]] = {}

    for part in body.split(delimiter):
        part = part.strip()
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        header_blob, value_blob = part.split(b"\r\n\r\n", 1)
        value = value_blob.rstrip(b"\r\n")
        headers = header_blob.decode("utf-8", errors="ignore").split("\r\n")
        content_disp = next((h for h in headers if h.lower().startswith("content-disposition:")), "")
        name_match = re.search(r'name="([^"]+)"', content_disp)
        if not name_match:
            continue
        field_name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', content_disp)
        filename = filename_match.group(1) if filename_match else None
        result[field_name] = (filename, value)

    return result


class RAGRequestHandler(BaseHTTPRequestHandler):
    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, status: int, body: bytes, cookies: list[str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if cookies:
            for c in cookies:
                self.send_header("Set-Cookie", c)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, cookies: list[str] | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        if cookies:
            for c in cookies:
                self.send_header("Set-Cookie", c)
        self.end_headers()

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        parsed = parse_qs(raw)
        return {k: v[0] for k, v in parsed.items()}

    def _current_user(self) -> dict[str, str] | None:
        cookie_header = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        session_id = cookie.get("session_id")
        if not session_id:
            return None
        return SESSIONS.get(session_id.value)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._json_response(HTTPStatus.OK, {"status": "ok"})
            return

        if path == "/":
            user = self._current_user()
            if user:
                self._redirect("/app")
                return
            body = render_html(
                "Вход | Company RAG KB",
                """
                <h1>Company RAG KB</h1>
                <p class='muted'>База знаний с ответами по внутренней документации.</p>
                <div class='alert'>
                  Тестовые пользователи: <b>admin/admin123</b> и <b>employee/employee123</b>
                </div>
                <form method='post' action='/login'>
                  <label>Логин</label>
                  <input name='username' placeholder='admin' required />
                  <label>Пароль</label>
                  <input type='password' name='password' placeholder='••••••' required />
                  <button type='submit'>Войти</button>
                </form>
                """,
            )
            self._html_response(HTTPStatus.OK, body)
            return

        if path == "/app":
            user = self._current_user()
            if not user:
                self._redirect("/")
                return

            admin_block = ""
            if user["role"] == "admin":
                admin_block = """
                <div class='card'>
                  <h2>Загрузка документов файлом (только для админа)</h2>
                  <form method='post' action='/documents/form' enctype='multipart/form-data'>
                    <label>Название документа</label>
                    <input name='title' required />
                    <label>Файл документа (txt/md)</label>
                    <input type='file' name='document_file' accept='.txt,.md,text/plain' required />
                    <button type='submit'>Загрузить файл</button>
                  </form>
                </div>
                """

            body = render_html(
                "Панель | Company RAG KB",
                f"""
                <h1>Панель знаний</h1>
                <p>Вы вошли как <b>{user['username']}</b> <span class='tag'>{user['role']}</span></p>
                <p><a href='/logout'>Выйти</a></p>
                {admin_block}
                <div class='card'>
                  <h2>Задать вопрос по документации</h2>
                  <form method='post' action='/ask/form'>
                    <label>Вопрос</label>
                    <textarea name='question' rows='4' required></textarea>
                    <label>Количество источников</label>
                    <select name='top_k'>
                      <option>3</option><option>4</option><option>5</option>
                    </select>
                    <button type='submit'>Получить ответ</button>
                  </form>
                </div>
                """,
            )
            self._html_response(HTTPStatus.OK, body)
            return

        if path == "/logout":
            cookie_header = self.headers.get("Cookie", "")
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            session_id = cookie.get("session_id")
            if session_id:
                SESSIONS.pop(session_id.value, None)
            self._redirect("/", cookies=["session_id=; Path=/; Max-Age=0; HttpOnly"])
            return

        self._redirect("/")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/login":
            form = self._read_form()
            username = form.get("username", "")
            password = form.get("password", "")
            record = USERS.get(username)
            if not record or record["password"] != password:
                body = render_html("Ошибка входа", "<h1>Ошибка входа</h1><p>Неверный логин или пароль.</p><a href='/'>Назад</a>")
                self._html_response(HTTPStatus.UNAUTHORIZED, body)
                return

            sid = secrets.token_hex(16)
            SESSIONS[sid] = {"username": username, "role": record["role"]}
            self._redirect("/app", cookies=[f"session_id={sid}; Path=/; HttpOnly; SameSite=Lax"])
            return

        if path == "/documents":
            user = self._current_user()
            if not user or user["role"] != "admin":
                self._json_response(HTTPStatus.FORBIDDEN, {"error": "admin only"})
                return

            content_type = self.headers.get("Content-Type", "")
            if content_type.startswith("multipart/form-data"):
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length) if length else b""
                fields = _parse_multipart_form_data(content_type, raw_body)
                title = fields.get("title", (None, b""))[1].decode("utf-8", errors="ignore").strip()
                file_name, file_bytes = fields.get("document_file", (None, b""))
                content = file_bytes.decode("utf-8", errors="ignore").strip()
                metadata = {"upload_type": "file", "filename": file_name or ""}
            else:
                payload = self._read_json()
                title = payload.get("title", "")
                content = payload.get("content", "")
                metadata = payload.get("metadata", {})

            if not title or not content:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": "title/content or title/document_file required"})
                return

            doc_id = str(uuid.uuid4())
            chunks = kb.add_document(doc_id, title, content, metadata)
            self._json_response(HTTPStatus.OK, {"document_id": doc_id, "chunks_created": chunks, "total_chunks": len(kb.chunks)})
            return

        if path == "/documents/form":
            user = self._current_user()
            if not user or user["role"] != "admin":
                self._html_response(HTTPStatus.FORBIDDEN, render_html("Доступ запрещён", "<h1>Только для админа</h1><a href='/app'>Назад</a>"))
                return

            content_type = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length) if length else b""
            fields = _parse_multipart_form_data(content_type, raw_body)
            title = fields.get("title", (None, b""))[1].decode("utf-8", errors="ignore").strip()
            file_name, file_bytes = fields.get("document_file", (None, b""))
            content = file_bytes.decode("utf-8", errors="ignore").strip()

            if not title or not content:
                self._html_response(HTTPStatus.BAD_REQUEST, render_html("Ошибка", "<h1>Нужны title и файл документа</h1><a href='/app'>Назад</a>"))
                return

            doc_id = str(uuid.uuid4())
            chunks = kb.add_document(doc_id, title, content, {"source": "web", "filename": file_name or ""})
            body = render_html("Документ загружен", f"<h1>Документ загружен</h1><p>Файл: <b>{file_name or 'unknown'}</b></p><p>Чанков создано: <b>{chunks}</b></p><a href='/app'>Назад</a>")
            self._html_response(HTTPStatus.OK, body)
            return

        if path == "/ask":
            user = self._current_user()
            if not user:
                self._json_response(HTTPStatus.UNAUTHORIZED, {"error": "auth required"})
                return
            payload = self._read_json()
            question = payload.get("question", "")
            top_k = int(payload.get("top_k", 4))
            if len(question) < 3:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": "question too short"})
                return

            matches = kb.retrieve(question, top_k=top_k)
            answer = SimpleAnswerGenerator.generate(question, matches)
            self._json_response(
                HTTPStatus.OK,
                {
                    "answer": answer,
                    "sources": [
                        {
                            "title": chunk.title,
                            "score": round(score, 4),
                            "excerpt": chunk.text[:220],
                            "metadata": chunk.metadata,
                        }
                        for chunk, score in matches
                    ],
                },
            )
            return

        if path == "/ask/form":
            user = self._current_user()
            if not user:
                self._redirect("/")
                return
            form = self._read_form()
            question = form.get("question", "")
            top_k = int(form.get("top_k", "4"))
            matches = kb.retrieve(question, top_k=top_k)
            answer = SimpleAnswerGenerator.generate(question, matches)
            source_items = "".join(f"<li><b>{chunk.title}</b> ({score:.2f})<br/>{chunk.text[:180]}</li>" for chunk, score in matches) or "<li>Источники не найдены</li>"
            body = render_html(
                "Ответ",
                f"""
                <h1>Ответ готов</h1>
                <p><a href='/app'>← Назад в панель</a></p>
                <div class='card'><pre>{answer}</pre></div>
                <div class='card'>
                  <h2>Источники</h2>
                  <ul class='sources'>{source_items}</ul>
                </div>
                """,
            )
            self._html_response(HTTPStatus.OK, body)
            return

        self._redirect("/")


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), RAGRequestHandler)
    print(f"RAG web app started at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
