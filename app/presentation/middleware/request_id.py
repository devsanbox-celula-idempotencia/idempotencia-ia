"""Middleware ASGI puro: asigna un X-Request-ID a cada petición.

Se implementa a nivel ASGI (y no con BaseHTTPMiddleware) para no interferir
con las respuestas en streaming del endpoint de chat.
"""
from __future__ import annotations

import secrets

from starlette.datastructures import Headers, MutableHeaders


class RequestIdMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = Headers(scope=scope).get("x-request-id") or secrets.token_hex(8)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        await self.app(scope, receive, send_wrapper)
