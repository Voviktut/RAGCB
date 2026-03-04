import json
import threading
import urllib.parse
import urllib.request

from app import main


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

        doc_payload = json.dumps(
            {
                "title": "Регламент онбординга",
                "content": "Новый сотрудник получает доступы в первый рабочий день после проверки ИБ.",
                "metadata": {"department": "HR"},
            }
        ).encode("utf-8")
        with admin_opener.open(
            urllib.request.Request(
                f"http://127.0.0.1:{port}/documents",
                data=doc_payload,
                headers={"Content-Type": "application/json"},
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
            assert "Ответ на основе" in data["answer"]
            assert len(data["sources"]) >= 1
    finally:
        server.shutdown()
        server.server_close()
