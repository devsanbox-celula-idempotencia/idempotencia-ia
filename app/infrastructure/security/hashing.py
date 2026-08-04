"""Hash de API keys con SHA-256. Nunca se guarda la clave en claro."""
from __future__ import annotations

import hashlib
import hmac

from app.domain.ports.services.password_hasher import KeyHasher


class Sha256KeyHasher(KeyHasher):
    def hash(self, raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def verify(self, raw_key: str, key_hash: str) -> bool:
        return hmac.compare_digest(self.hash(raw_key), key_hash)
