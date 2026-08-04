"""Puerto para generar y verificar el hash de las API keys."""
from __future__ import annotations

from abc import ABC, abstractmethod


class KeyHasher(ABC):
    @abstractmethod
    def hash(self, raw_key: str) -> str: ...

    @abstractmethod
    def verify(self, raw_key: str, key_hash: str) -> bool: ...


class KeyGenerator(ABC):
    @abstractmethod
    def generate(self) -> str:
        """Devuelve una clave nueva con el formato sk_live_..."""
