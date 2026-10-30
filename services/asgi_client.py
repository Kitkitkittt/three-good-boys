"""Minimal in-process ASGI driver for tests (no httpx/TestClient dependency)."""
import asyncio
import json


def request(app, method, path, headers=None, json_body=None, raw_body=None):
    """Call an ASGI app once and return a :class:`Response`."""
    body = raw_body if raw_body is not None else (b"" if json_body is None else json.dumps(json_body).encode())
    header_list = [(b"host", b"test")]
    for key, value in (headers or {}).items():
        header_list.append((key.lower().encode(), str(value).encode()))
    if json_body is not None and not any(k == b"content-type" for k, _ in header_list):
        header_list.append((b"content-type", b"application/json"))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": header_list,
        "scheme": "http",
        "server": ("test", 80),
        "client": ("127.0.0.1", 1),
    }
    sent = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return Response(sent)


class Response:
    def __init__(self, messages):
        self.status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        self.body = body
        try:
            self.json = json.loads(body) if body else None
        except ValueError:
            self.json = None

    @property
    def code(self):
        return (self.json or {}).get("code")
