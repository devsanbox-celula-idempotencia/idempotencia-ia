"""Prueba de extremo a extremo contra un despliegue real.

No se ejecuta por defecto. Necesita el gateway levantado, Ollama con
qwen2.5:3b y una API key válida:

    GATEWAY_URL=http://localhost:8000 GATEWAY_KEY=sk_live_... pytest tests/e2e -v
"""
from __future__ import annotations

import os

import pytest

URL = os.getenv("GATEWAY_URL")
KEY = os.getenv("GATEWAY_KEY")

pytestmark = pytest.mark.skipif(
    not (URL and KEY), reason="Define GATEWAY_URL y GATEWAY_KEY para ejecutar los e2e"
)


@pytest.fixture
def client():
    openai = pytest.importorskip("openai")
    return openai.OpenAI(api_key=KEY, base_url=f"{URL}/v1")


def test_listar_modelos(client) -> None:
    assert "qwen2.5:3b" in [m.id for m in client.models.list().data]


def test_chat(client) -> None:
    r = client.chat.completions.create(
        model="qwen2.5:3b", messages=[{"role": "user", "content": "Di solo: ok"}]
    )
    assert r.choices[0].message.content
    assert r.usage.total_tokens > 0


def test_streaming(client) -> None:
    trozos = [
        c.choices[0].delta.content or ""
        for c in client.chat.completions.create(
            model="qwen2.5:3b",
            messages=[{"role": "user", "content": "Cuenta del 1 al 3"}],
            stream=True,
        )
    ]
    assert "".join(trozos).strip()


def test_modelo_no_permitido(client) -> None:
    openai = pytest.importorskip("openai")
    with pytest.raises(openai.NotFoundError):
        client.chat.completions.create(
            model="llama3:70b", messages=[{"role": "user", "content": "hola"}]
        )


def test_clave_invalida() -> None:
    openai = pytest.importorskip("openai")
    malo = openai.OpenAI(api_key="sk_live_no_existe", base_url=f"{URL}/v1")
    with pytest.raises(openai.AuthenticationError):
        malo.models.list()
