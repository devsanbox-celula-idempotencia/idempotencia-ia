"""OllamaClient y OllamaProvider contra un Ollama simulado con respx.

Es la única capa que habla el protocolo real de Ollama: si cambia el nombre de
un campo (`prompt_eval_count`, `eval_count`, `done_reason`), estos tests lo
detectan aunque los dobles del resto de la suite sigan pasando.
"""
from __future__ import annotations

import json

import pytest

respx = pytest.importorskip("respx", reason="respx está en requirements-dev.txt")
import httpx  # noqa: E402

from app.domain.exceptions import ProviderError  # noqa: E402
from app.infrastructure.llm.ollama_client import OllamaClient  # noqa: E402
from app.infrastructure.llm.ollama_provider import OllamaProvider  # noqa: E402

BASE = "http://ollama-de-prueba:11434"


@pytest.fixture
async def provider():
    cliente = OllamaClient(base_url=BASE, timeout=5)
    try:
        yield OllamaProvider(cliente)
    finally:
        await cliente.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_chat_devuelve_texto_consumo_y_finish_reason(provider) -> None:
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Hola"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 29,
                "eval_count": 119,
            },
        )
    )

    contenido, usage, finish_reason = await provider.chat(
        "qwen2.5:3b", [{"role": "user", "content": "Hola"}]
    )
    assert contenido == "Hola"
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (29, 119, 148)
    assert finish_reason == "stop"


@pytest.mark.asyncio
@respx.mock
async def test_chat_finish_reason_length(provider) -> None:
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": "cor"}, "done": True, "done_reason": "length",
                  "prompt_eval_count": 5, "eval_count": 3},
        )
    )
    _, _, finish_reason = await provider.chat("qwen2.5:3b", [])
    assert finish_reason == "length"


@pytest.mark.asyncio
@respx.mock
async def test_chat_sin_contadores_no_revienta(provider) -> None:
    """Algunos backends no reportan tokens: debe devolver 0, no fallar."""
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "x"}, "done": True})
    )
    _, usage, _ = await provider.chat("qwen2.5:3b", [])
    assert usage.total_tokens == 0


@pytest.mark.asyncio
@respx.mock
async def test_las_options_viajan_en_el_cuerpo(provider) -> None:
    ruta = respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "x"}, "done": True})
    )
    await provider.chat("qwen2.5:3b", [{"role": "user", "content": "x"}], temperature=0.5)

    enviado = json.loads(ruta.calls[0].request.content)
    assert enviado["model"] == "qwen2.5:3b"
    assert enviado["options"] == {"temperature": 0.5}
    assert enviado["stream"] is False


@pytest.mark.asyncio
@respx.mock
async def test_streaming_parsea_ndjson(provider) -> None:
    """Ollama devuelve un objeto JSON por línea, no SSE."""
    lineas = (
        b'{"message":{"role":"assistant","content":"Ho"},"done":false}\n'
        b'{"message":{"content":"la"},"done":false}\n'
        b'{"message":{"content":""},"done":true,"done_reason":"stop",'
        b'"prompt_eval_count":7,"eval_count":2}\n'
    )
    respx.post(f"{BASE}/api/chat").mock(return_value=httpx.Response(200, content=lineas))

    trozos = [c async for c in provider.chat_stream("qwen2.5:3b", [])]
    assert len(trozos) == 3
    assert "".join(t["message"].get("content", "") for t in trozos) == "Hola"
    assert trozos[-1]["done"] is True
    assert trozos[-1]["prompt_eval_count"] == 7


@pytest.mark.asyncio
@respx.mock
async def test_lineas_vacias_del_stream_se_ignoran(provider) -> None:
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            content=b'{"message":{"content":"a"},"done":false}\n\n{"message":{"content":""},"done":true}\n',
        )
    )
    trozos = [c async for c in provider.chat_stream("qwen2.5:3b", [])]
    assert len(trozos) == 2


@pytest.mark.asyncio
@respx.mock
async def test_error_http_se_convierte_en_provider_error(provider) -> None:
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(500, text="model not found")
    )
    with pytest.raises(ProviderError) as exc:
        await provider.chat("qwen2.5:3b", [])
    assert "500" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_ollama_inalcanzable_se_convierte_en_provider_error(provider) -> None:
    respx.post(f"{BASE}/api/chat").mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(ProviderError):
        await provider.chat("qwen2.5:3b", [])


@pytest.mark.asyncio
@respx.mock
async def test_listar_modelos(provider) -> None:
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "qwen2.5:3b"}, {"name": "nomic-embed-text"}]}
        )
    )
    modelos = await provider.list_models()
    assert [m.id for m in modelos] == ["qwen2.5:3b", "nomic-embed-text"]
    assert all(m.owned_by == "ollama" for m in modelos)


@pytest.mark.asyncio
@respx.mock
async def test_embeddings(provider) -> None:
    respx.post(f"{BASE}/api/embed").mock(
        return_value=httpx.Response(
            200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]], "prompt_eval_count": 6}
        )
    )
    vectores, usage = await provider.embeddings("nomic-embed-text", ["a", "b"])
    assert vectores == [[0.1, 0.2], [0.3, 0.4]]
    assert usage.prompt_tokens == 6


@pytest.mark.asyncio
@respx.mock
async def test_embeddings_vacios_dan_provider_error(provider) -> None:
    """Es lo que ocurre si se pide embeddings a un modelo de chat."""
    respx.post(f"{BASE}/api/embed").mock(return_value=httpx.Response(200, json={"embeddings": []}))
    with pytest.raises(ProviderError):
        await provider.embeddings("qwen2.5:3b", ["a"])


@pytest.mark.asyncio
@respx.mock
async def test_health(provider) -> None:
    respx.get(f"{BASE}/api/version").mock(return_value=httpx.Response(200, json={"version": "0.5"}))
    assert await provider.health() is True


@pytest.mark.asyncio
@respx.mock
async def test_health_falso_si_no_responde(provider) -> None:
    respx.get(f"{BASE}/api/version").mock(side_effect=httpx.ConnectError("nope"))
    assert await provider.health() is False
