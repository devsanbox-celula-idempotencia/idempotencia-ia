"""Entidad RequestLog: auditoría de cada petición atendida."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Límites de las columnas de la tabla RequestLogs.
# SQL Server NO trunca: aborta el INSERT con "String or binary data would be
# truncated". Y como el fallo de auditoría se traga para no romper la respuesta,
# el resultado sería consumo sin registrar. Se recorta aquí, en un solo sitio.
MAX_CLIENT_IP = 45
MAX_ERROR = 1000


def _clamp_nvarchar(value: str | None, max_units: int) -> str | None:
    """Recorta contando unidades UTF-16, que es como mide NVARCHAR.

    Un emoji ocupa 1 punto de código en Python pero 2 unidades UTF-16, así que
    `texto[:1000]` puede seguir sin caber en un NVARCHAR(1000).
    """
    if value is None:
        return None
    encoded = value.encode("utf-16-le")
    if len(encoded) <= max_units * 2:
        return value
    return encoded[: max_units * 2].decode("utf-16-le", "ignore")


@dataclass(slots=True)
class RequestLog:
    api_key_id: int | None
    model: str
    endpoint: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    status_code: int = 200
    client_ip: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        self.client_ip = _clamp_nvarchar(self.client_ip, MAX_CLIENT_IP)
        self.error = _clamp_nvarchar(self.error, MAX_ERROR)
        self.model = _clamp_nvarchar(self.model, 100) or ""
        self.endpoint = _clamp_nvarchar(self.endpoint, 100) or ""
