"""Personalización del esquema OpenAPI que alimenta Swagger UI."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

TAGS_METADATA: list[dict[str, Any]] = [
    {
        "name": "OpenAI Compatible",
        "description": (
            "Endpoints que replican la API de OpenAI. Los clientes solo cambian "
            "`base_url`; el SDK oficial funciona sin modificaciones."
        ),
    },
    {"name": "Admin", "description": "Gestión de API keys, consumo y logs. Requiere `X-Admin-Token`."},
    {"name": "Health", "description": "Liveness y readiness del gateway."},
]

DESCRIPTION = """
Gateway **compatible con OpenAI** sobre Ollama (`qwen2.5:3b`).

El cliente nunca habla con Ollama: habla con esta API, que se encarga de
autenticación por API key, límites de uso, conteo de tokens, auditoría y
traducción de formatos.

```python
from openai import OpenAI

client = OpenAI(api_key="sk_live_xxx", base_url="http://localhost:8000/v1")

resp = client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Hola"}],
)
```

**Autenticación:** `Authorization: Bearer sk_live_...` (botón *Authorize*).
"""


def custom_openapi(app: FastAPI):
    def _openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=DESCRIPTION,
            routes=app.routes,
            tags=TAGS_METADATA,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "description": "Clave del gateway con formato sk_live_...",
        }
        app.openapi_schema = schema
        return schema

    return _openapi
