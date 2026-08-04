"""Excepciones de dominio. La capa presentation las traduce a errores HTTP
con el formato de error de OpenAI."""
from __future__ import annotations


class DomainError(Exception):
    """Base de todos los errores de negocio."""


class InvalidApiKeyError(DomainError):
    """La clave no existe, está inactiva o expiró."""


class RateLimitExceededError(DomainError):
    """Se superó el límite de peticiones por minuto.

    `retry_after` son los segundos que el cliente debe esperar; la capa HTTP lo
    traduce a la cabecera `Retry-After`, que es lo que un frontend necesita para
    reintentar sin adivinar.
    """

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class QuotaExceededError(DomainError):
    """Se agotó la cuota del plan (diaria o mensual)."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ModelNotFoundError(DomainError):
    """El modelo solicitado no está habilitado en el gateway."""


class ProviderError(DomainError):
    """Fallo al comunicarse con el backend (Ollama)."""
