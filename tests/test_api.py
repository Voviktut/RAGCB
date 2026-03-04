import json
import threading
import urllib.parse
import urllib.request

from app import main


def _build_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]], boundary: str) -> bytes:
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    for name, (filename, content) in files.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                b"Content-Type: text/plain\r\n\r\n",
                content,
                b"\r\n",
            ]
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def test_http_flow_with_roles() -> None:
    main.SESSIONS.clear()
    main.kb._chunks.clear()

    server = main.ThreadingHTTPServer(("127.0.0.1", 0), main.RAGRequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            assert body["status"] == "ok"

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/preview") as resp:
            assert resp.status in (200, 303)

        admin_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        employee_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

        admin_login = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode("utf-8")
        admin_opener.open(
            urllib.request.Request(
                f"http://127.0.0.1:{port}/login",
                data=admin_login,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        )

        boundary = "----RAGBoundary"
        multipart = _build_multipart(
            fields={"title": "Регламент онбординга"},
            files={"document_file": ("onboarding.txt", "Новый сотрудник получает доступы в первый рабочий день после проверки ИБ.".encode("utf-8"))},
            boundary=boundary,
        )

        with admin_opener.open(
            urllib.request.Request(
                f"http://127.0.0.1:{port}/documents",
                data=multipart,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["chunks_created"] >= 1

        user_login = urllib.parse.urlencode({"username": "employee", "password": "employee123"}).encode("utf-8")
        employee_opener.open(
            urllib.request.Request(
                f"http://127.0.0.1:{port}/login",
                data=user_login,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        )

        ask_payload = json.dumps({"question": "Когда выдаются доступы новичку?", "top_k": 3}).encode("utf-8")
        with employee_opener.open(
            urllib.request.Request(
                f"http://127.0.0.1:{port}/ask",
                data=ask_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["answer"].strip() != ""
            assert len(data["sources"]) >= 1
            assert data["sources"][0]["metadata"].get("filename") == "onboarding.txt"
            assert data["sources"][0]["metadata"].get("section") is not None or data["sources"][0]["metadata"].get("page") is not None
    finally:
        server.shutdown()
        server.server_close()
