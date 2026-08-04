"""Middleware ASGI puro: mide latencia y deja un log por petición."""
from __future__ import annotations

import time

from starlette.datastructures import MutableHeaders

from app.infrastructure.observability.logger import get_logger

logger = get_logger("api")


class LoggingMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                duration_ms = int((time.perf_counter() - started) * 1000)
                MutableHeaders(scope=message)["X-Response-Time-Ms"] = str(duration_ms)
                logger.info(
                    "%s %s -> %s (%s ms) [req=%s]",
                    scope.get("method"),
                    scope.get("path"),
                    message["status"],
                    duration_ms,
                    scope.get("state", {}).get("request_id", "-"),
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
