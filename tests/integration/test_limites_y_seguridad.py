"""Límites, ramas de seguridad y errores no controlados.

Cubre las ramas que el resto de la suite no toca: rate limiting en todos los
endpoints, /ready con DEBUG apagado, el handler genérico de 500 y las entradas
que antes provocaban un 500 en vez del código correcto.
"""
from __future__ import annotations

import pytest


# --------------------------------------------------------------- rate limiting
@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"),
    [
        ("post", "/v1/chat/completions", {"model": "qwen2.5:3b",
                                          "messages": [{"role": "user", "content": "x"}]}),
        ("post", "/v1/completions", {"model": "qwen2.5:3b", "prompt": "x"}),
        ("post", "/v1/embeddings", {"model": "qwen2.5:3b", "input": "x"}),
        ("get", "/v1/models", None),
    ],
)
def test_todos_los_endpoints_v1_respetan_el_limite(client, auth, uow, metodo, ruta, cuerpo) -> None:
    """/v1/models se quedó sin limitador en una versión anterior."""
    uow.api_keys.items[1].requests_per_minute = 1

    primera = client.request(metodo.upper(), ruta, json=cuerpo, headers=auth)
    assert primera.status_code == 200, ruta

    segunda = client.request(metodo.upper(), ruta, json=cuerpo, headers=auth)
    assert segunda.status_code == 429, ruta
    assert segunda.json()["error"]["type"] == "rate_limit_error"


def test_con_el_limitador_desactivado_no_hay_429(client, auth, cuerpo_chat, uow, settings) -> None:
    settings.RATE_LIMIT_ENABLED = False
    uow.api_keys.items[1].requests_per_minute = 1
    for _ in range(3):
        r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
        assert r.status_code == 200


# --------------------------------------------------------------- /ready y fugas
def test_ready_no_filtra_detalles_con_debug_apagado(client, session, settings) -> None:
    """El mensaje de error de la base de datos incluye host y usuario."""
    settings.DEBUG = False
    session.fallo = RuntimeError("login failed for user 'sa' en 10.0.0.5")

    cuerpo = client.get("/ready").json()
    assert cuerpo["status"] == "degraded"
    assert cuerpo["database"] is False
    assert "database_error" not in cuerpo
    assert "database_url" not in cuerpo


# --------------------------------------------------------------- errores 500
def test_error_inesperado_devuelve_500_con_formato_openai(client, auth, cuerpo_chat, provider) -> None:
    """Un fallo no previsto no debe filtrar la traza al cliente."""
    provider.fallo = ValueError("algo raro de una librería interna")

    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
    assert r.status_code == 500
    error = r.json()["error"]
    assert error["type"] == "api_error"
    assert error["message"] == "Error interno del servidor"
    assert "algo raro" not in r.text


def test_ruta_inexistente_devuelve_404_con_formato_openai(client) -> None:
    r = client.get("/v1/no-existe")
    assert r.status_code == 404
    assert "error" in r.json()


def test_metodo_no_permitido(client, auth) -> None:
    assert client.get("/v1/chat/completions", headers=auth).status_code == 405


# --------------------------------------------------------------- admin token
def test_token_de_admin_con_caracteres_no_ascii_devuelve_403(client) -> None:
    """compare_digest sobre dos `str` lanza TypeError si hay no-ASCII, y eso
    convertía un 403 en un 500."""
    # En bytes: httpx codifica los valores de cabecera `str` en ASCII y ni
    # siquiera llegaría a enviarse.
    r = client.get("/admin/logs", headers={"X-Admin-Token": "café-con-acentos".encode()})
    assert r.status_code == 403


def test_token_de_admin_vacio(client) -> None:
    assert client.get("/admin/logs", headers={"X-Admin-Token": ""}).status_code == 403


# --------------------------------------------------------------- stop
def test_stop_escalar_largo_es_valido(client, auth, provider) -> None:
    """El tope de 4 es de SECUENCIAS, no de caracteres: stop='<|im_end|>' vale."""
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:3b",
            "messages": [{"role": "user", "content": "x"}],
            "stop": "<|im_end|>",
        },
        headers=auth,
    )
    assert r.status_code == 200
    assert provider.llamadas[0]["options"]["stop"] == ["<|im_end|>"]


def test_mas_de_cuatro_secuencias_de_parada(client, auth) -> None:
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:3b",
            "messages": [{"role": "user", "content": "x"}],
            "stop": ["a", "b", "c", "d", "e"],
        },
        headers=auth,
    )
    assert r.status_code == 422


def test_penalizaciones_fuera_de_rango(client, auth) -> None:
    for campo in ("presence_penalty", "frequency_penalty"):
        for valor in (10, -10):
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "qwen2.5:3b",
                    "messages": [{"role": "user", "content": "x"}],
                    campo: valor,
                },
                headers=auth,
            )
            assert r.status_code == 422, (campo, valor)


def test_completions_propaga_las_penalizaciones(client, auth, provider) -> None:
    """Regresión: este endpoint las validaba pero las descartaba en silencio."""
    client.post(
        "/v1/completions",
        json={"model": "qwen2.5:3b", "prompt": "x", "presence_penalty": 1.5},
        headers=auth,
    )
    assert provider.llamadas[0]["options"]["presence_penalty"] == 1.5


# --------------------------------------------------------------- modelos con /
def test_modelo_con_barra_en_la_ruta(client, auth, uow, settings) -> None:
    """El converter :path debe dejar pasar nombres tipo `biblioteca/modelo`."""
    from app.domain.entities.model import LLMModel

    uow.models.items.append(LLMModel(id="biblioteca/qwen", provider_model="biblioteca/qwen"))
    settings.ALLOWED_MODELS = ["qwen2.5:3b", "biblioteca/qwen"]

    r = client.get("/v1/models/biblioteca/qwen", headers=auth)
    assert r.status_code == 200
    assert r.json()["id"] == "biblioteca/qwen"
