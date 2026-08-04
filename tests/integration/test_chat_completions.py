"""POST /v1/chat/completions — el endpoint principal."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.domain.entities.usage import Usage
from app.domain.exceptions import ProviderError


# --------------------------------------------------------------------- camino feliz
def test_respuesta_con_formato_de_openai(client, auth, cuerpo_chat) -> None:
    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["object"] == "chat.completion"
    assert cuerpo["id"].startswith("chatcmpl-")
    assert cuerpo["model"] == "qwen2.5:3b"
    assert cuerpo["choices"][0]["message"] == {
        "role": "assistant",
        "content": "Hola desde el modelo",
        "name": None,
    }
    assert cuerpo["choices"][0]["finish_reason"] == "stop"
    assert cuerpo["usage"] == {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}


def test_registra_consumo_y_log(client, auth, cuerpo_chat, uow) -> None:
    client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)

    assert len(uow.logs.items) == 1
    log = uow.logs.items[0]
    assert (log.api_key_id, log.endpoint, log.status_code) == (1, "/v1/chat/completions", 200)
    assert log.total_tokens == 15
    assert (log.prompt_tokens, log.completion_tokens) == (11, 4)

    hoy = datetime.now(timezone.utc).date()
    assert uow.usage.items[(1, hoy)].total_tokens == 15
    assert uow.usage.items[(1, hoy)].requests == 1


def test_suelta_la_conexion_antes_de_llamar_al_modelo(
    client, auth, cuerpo_chat, uow, provider
) -> None:
    """Regresión del error 08S01: la conexión no puede quedar retenida durante
    la inferencia, que puede tardar decenas de segundos.

    No basta con comprobar que se cerró: hay que comprobar el ORDEN, porque el
    bug consistía exactamente en cerrarla después.
    """
    cerrada_al_invocar: list[int] = []
    original = provider.chat

    async def espia(*args, **kwargs):
        cerrada_al_invocar.append(uow.closed)
        return await original(*args, **kwargs)

    provider.chat = espia
    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
    assert r.status_code == 200
    assert cerrada_al_invocar == [1]


def test_parametros_se_traducen_a_options_de_ollama(client, auth, provider) -> None:
    client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:3b",
            "messages": [{"role": "user", "content": "Hola"}],
            "temperature": 0.5,
            "top_p": 0.9,
            "max_tokens": 128,
            "stop": "FIN",
            "presence_penalty": 1.0,
            "frequency_penalty": -1.0,
        },
        headers=auth,
    )
    opciones = provider.llamadas[0]["options"]
    assert opciones == {
        "temperature": 0.5,
        "top_p": 0.9,
        "num_predict": 128,
        "stop": ["FIN"],
        "presence_penalty": 1.0,
        "frequency_penalty": -1.0,
    }


def test_stop_vacio_no_llega_al_modelo(client, auth, provider) -> None:
    """Una secuencia de parada vacía cortaría la generación en el token 0."""
    client.post(
        "/v1/chat/completions",
        json={"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "x"}], "stop": [""]},
        headers=auth,
    )
    assert "stop" not in provider.llamadas[0]["options"]


def test_temperatura_cero_se_envia(client, auth, provider) -> None:
    """0 es falsy: comprobar que no se pierde por un `if not`."""
    client.post(
        "/v1/chat/completions",
        json={"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "x"}], "temperature": 0},
        headers=auth,
    )
    assert provider.llamadas[0]["options"]["temperature"] == 0


def test_finish_reason_length_se_propaga(client, auth, cuerpo_chat, provider) -> None:
    """Sin esto el cliente no distingue una respuesta cortada de una completa."""
    provider.finish_reason = "length"
    cuerpo = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth).json()
    assert cuerpo["choices"][0]["finish_reason"] == "length"


# --------------------------------------------------------------------- streaming
def _eventos(texto: str) -> list[dict]:
    return [
        json.loads(linea[6:])
        for linea in texto.splitlines()
        if linea.startswith("data: ") and linea != "data: [DONE]"
    ]


def test_streaming_formato_sse(client, auth, cuerpo_chat) -> None:
    r = client.post("/v1/chat/completions", json={**cuerpo_chat, "stream": True}, headers=auth)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text.rstrip().endswith("data: [DONE]")

    eventos = _eventos(r.text)
    assert all(e["object"] == "chat.completion.chunk" for e in eventos)
    assert "".join(e["choices"][0]["delta"].get("content", "") for e in eventos) == "Hola"
    assert eventos[-1]["choices"][0]["finish_reason"] == "stop"


def test_streaming_primer_chunk_lleva_el_rol(client, auth, cuerpo_chat) -> None:
    r = client.post("/v1/chat/completions", json={**cuerpo_chat, "stream": True}, headers=auth)
    assert _eventos(r.text)[0]["choices"][0]["delta"]["role"] == "assistant"


def test_streaming_rol_aunque_el_primer_chunk_venga_vacio(client, auth, cuerpo_chat, provider) -> None:
    """Ollama suele emitir un primer chunk con content vacío."""
    provider.chunks = [
        {"message": {"role": "assistant", "content": ""}, "done": False},
        {"message": {"role": "assistant", "content": "Ho"}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 11, "eval_count": 4},
    ]
    r = client.post("/v1/chat/completions", json={**cuerpo_chat, "stream": True}, headers=auth)
    assert _eventos(r.text)[0]["choices"][0]["delta"]["role"] == "assistant"


def test_streaming_no_pierde_el_texto_del_ultimo_chunk(client, auth, cuerpo_chat, provider) -> None:
    provider.chunks = [
        {
            "message": {"role": "assistant", "content": "todo de una vez"},
            "done": True,
            "prompt_eval_count": 11,
            "eval_count": 4,
        }
    ]
    r = client.post("/v1/chat/completions", json={**cuerpo_chat, "stream": True}, headers=auth)
    texto = "".join(e["choices"][0]["delta"].get("content", "") for e in _eventos(r.text))
    assert texto == "todo de una vez"


def test_streaming_registra_el_consumo_al_cerrar(client, auth, cuerpo_chat, uow) -> None:
    client.post("/v1/chat/completions", json={**cuerpo_chat, "stream": True}, headers=auth)
    assert len(uow.logs.items) == 1
    assert uow.logs.items[0].total_tokens == 15


def test_streaming_finish_reason_length(client, auth, cuerpo_chat, provider) -> None:
    provider.finish_reason = "length"
    r = client.post("/v1/chat/completions", json={**cuerpo_chat, "stream": True}, headers=auth)
    assert _eventos(r.text)[-1]["choices"][0]["finish_reason"] == "length"


def test_streaming_error_del_backend_devuelve_502_limpio(client, auth, cuerpo_chat, provider) -> None:
    """El primer chunk se consume antes de responder, así que todavía se puede
    devolver un error HTTP en vez de un stream truncado."""
    provider.fallo = ProviderError("Ollama no responde")
    r = client.post("/v1/chat/completions", json={**cuerpo_chat, "stream": True}, headers=auth)
    assert r.status_code == 502
    assert r.json()["error"]["type"] == "api_error"


def test_streaming_sin_chunks_devuelve_502(client, auth, cuerpo_chat, provider) -> None:
    provider.chunks = []
    r = client.post("/v1/chat/completions", json={**cuerpo_chat, "stream": True}, headers=auth)
    assert r.status_code == 502


# --------------------------------------------------------------------- errores
def test_modelo_no_permitido_devuelve_404(client, auth) -> None:
    r = client.post(
        "/v1/chat/completions",
        json={"model": "llama3:70b", "messages": [{"role": "user", "content": "x"}]},
        headers=auth,
    )
    assert r.status_code == 404
    assert r.json()["error"]["type"] == "model_not_found"


def test_n_mayor_que_uno_devuelve_400(client, auth, cuerpo_chat) -> None:
    r = client.post("/v1/chat/completions", json={**cuerpo_chat, "n": 3}, headers=auth)
    assert r.status_code == 400


def test_error_del_proveedor_devuelve_502_y_queda_auditado(client, auth, cuerpo_chat, provider, uow) -> None:
    provider.fallo = ProviderError("Ollama caído")
    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
    assert r.status_code == 502
    assert uow.logs.items[0].status_code == 502
    assert "Ollama caído" in uow.logs.items[0].error


def test_sin_autenticacion_devuelve_401(client, cuerpo_chat) -> None:
    assert client.post("/v1/chat/completions", json=cuerpo_chat).status_code == 401


def test_validaciones(client, auth) -> None:
    casos = [
        {"model": "qwen2.5:3b", "messages": []},
        {"model": "qwen2.5:3b", "messages": [{"role": "usuario", "content": "x"}]},
        {"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "x"}], "temperature": 3},
        {"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "x"}], "top_p": 2},
        {"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "x"}], "max_tokens": 0},
        {"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "x"}], "n": 0},
        {"messages": [{"role": "user", "content": "x"}], "temperature": "mucha"},
    ]
    for caso in casos:
        r = client.post("/v1/chat/completions", json=caso, headers=auth)
        assert r.status_code == 422, caso


def test_el_422_no_devuelve_el_cuerpo_entero(client, auth) -> None:
    """Un cuerpo inválido grande no debe amplificarse en la respuesta."""
    grande = {"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "x" * 50_000}], "n": "no"}
    r = client.post("/v1/chat/completions", json=grande, headers=auth)
    assert r.status_code == 422
    assert len(r.content) < 2_000


# --------------------------------------------------------------------- límites
def test_rate_limit_por_minuto(client, auth, cuerpo_chat, uow) -> None:
    uow.api_keys.items[1].requests_per_minute = 1
    assert client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth).status_code == 200
    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
    assert r.status_code == 429
    assert r.json()["error"]["type"] == "rate_limit_error"


def test_cuota_diaria_agotada(client, auth, cuerpo_chat, uow) -> None:
    hoy = datetime.now(timezone.utc).date()
    uow.api_keys.items[1].daily_token_limit = 100
    uow.usage.items[(1, hoy)] = Usage(
        api_key_id=1, day=hoy, prompt_tokens=500, total_tokens=500, requests=1
    )
    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
    assert r.status_code == 429
    assert r.json()["error"]["type"] == "insufficient_quota"


def test_cuota_no_agotada_deja_pasar(client, auth, cuerpo_chat, uow) -> None:
    hoy = datetime.now(timezone.utc).date()
    uow.api_keys.items[1].daily_token_limit = 1000
    uow.usage.items[(1, hoy)] = Usage(api_key_id=1, day=hoy, total_tokens=10, requests=1)
    assert client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth).status_code == 200


# --------------------------------------------------------------------- client_ip
def test_x_forwarded_for_basura_no_rompe_la_peticion(client, auth, cuerpo_chat, uow) -> None:
    """Regresión: un XFF largo desbordaba ClientIp NVARCHAR(45) y hacía perder
    el registro entero, permitiendo consumo sin auditar."""
    r = client.post(
        "/v1/chat/completions",
        json=cuerpo_chat,
        headers={**auth, "X-Forwarded-For": "A" * 4000},
    )
    assert r.status_code == 200
    # La cabecera no es una IP válida: se descarta y se usa la real del cliente.
    assert uow.logs.items[0].client_ip == "testclient"


def test_x_forwarded_for_valido_se_usa(client, auth, cuerpo_chat, uow) -> None:
    client.post(
        "/v1/chat/completions",
        json=cuerpo_chat,
        headers={**auth, "X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
    )
    assert uow.logs.items[0].client_ip == "203.0.113.9"
