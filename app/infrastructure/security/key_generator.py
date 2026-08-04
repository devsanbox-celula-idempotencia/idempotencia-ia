"""Generación de API keys con formato sk_live_<aleatorio>."""
from __future__ import annotations

import secrets

from app.domain.ports.services.password_hasher import KeyGenerator


class SecretsKeyGenerator(KeyGenerator):
    def __init__(self, prefix: str = "sk_live_", nbytes: int = 24) -> None:
        self._prefix = prefix
        self._nbytes = nbytes

    def generate(self) -> str:
        return f"{self._prefix}{secrets.token_urlsafe(self._nbytes)}"

    @staticmethod
    def visible_prefix(raw_key: str, length: int = 12) -> str:
        """Lo que se muestra en el panel para identificar la clave."""
        return raw_key[:length]
