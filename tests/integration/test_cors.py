"""CORS y cabeceras de límite.

Ojo: el middleware de CORS se configura en `create_app()` con los settings que
se leen al importar la aplicación, así que estas pruebas usan los orígenes
reales del `.env` (a diferencia del resto de la suite, que los sustituye).
"""
from __future__ import annotations

import pytest

from app.infrastructure.config.settings import get_settings

ORIGENES = get_settings().CORS_ORIGINS
ORIGEN_PERMITIDO = next((o for o in ORIGENES if o != "*"), None)

sin_lista_blanca = pytest.mark.skipif(
    ORIGEN_PERMITIDO is None,
    reason="CORS_ORIGINS es ['*']: no hay lista blanca que comprobar",
)


@sin_lista_blanca
def test_preflight_de_un_origen_permitido(client) -> None:
    """El navegador manda un OPTIONS antes del POST real."""
    r = client.options(
        "/v1/chat/completions",
        headers={
            "Origin": ORIGEN_PERMITIDO,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGEN_PERMITIDO
    assert "POST" in r.headers["access-control-allow-methods"]
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


@sin_lista_blanca
def test_origen_no_permitido_no_recibe_la_cabecera(client) -> None:
    """Sin `access-control-allow-origin`, el navegador bloquea la respuesta."""
    r = client.options(
        "/v1/chat/completions",
        headers={
            "Origin": "https://sitio-no-autorizado.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in r.headers


@sin_lista_blanca
def test_respuesta_real_lleva_allow_origin(client, auth, cuerpo_chat) -> None:
    r = client.post(
        "/v1/chat/completions",
        json=cuerpo_chat,
        headers={**auth, "Origin": ORIGEN_PERMITIDO},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGEN_PERMITIDO


@sin_lista_blanca
def test_las_cabeceras_utiles_estan_expuestas(client, auth, cuerpo_chat) -> None:
    """Sin `expose_headers`, el navegador NO deja leerlas desde JavaScript
    aunque viajen en la respuesta."""
    r = client.post(
        "/v1/chat/completions",
        json=cuerpo_chat,
        headers={**auth, "Origin": ORIGEN_PERMITIDO},
    )
    expuestas = r.headers.get("access-control-expose-headers", "").lower()
    for cabecera in ("x-request-id", "x-response-time-ms", "retry-after", "x-ratelimit-remaining"):
        assert cabecera in expuestas, cabecera


# --------------------------------------------------------------- rate limit
def test_cabeceras_de_limite_en_respuesta_correcta(client, auth, cuerpo_chat, uow) -> None:
    uow.api_keys.items[1].requests_per_minute = 10
    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)

    assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == "10"
    assert r.headers["X-RateLimit-Remaining"] == "9"
    assert int(r.headers["X-RateLimit-Reset"]) <= 60


def test_retry_after_al_superar_el_limite(client, auth, cuerpo_chat, uow) -> None:
    """El frontend necesita saber cuánto esperar sin adivinar."""
    uow.api_keys.items[1].requests_per_minute = 1
    client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)

    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
    assert r.status_code == 429
    assert 0 < int(r.headers["Retry-After"]) <= 60


def test_retry_after_al_agotar_la_cuota_apunta_a_medianoche(client, auth, cuerpo_chat, uow) -> None:
    """La cuota diaria no se reinicia en segundos, sino a medianoche UTC."""
    from datetime import datetime, timezone

    from app.domain.entities.usage import Usage

    hoy = datetime.now(timezone.utc).date()
    uow.api_keys.items[1].daily_token_limit = 10
    uow.usage.items[(1, hoy)] = Usage(api_key_id=1, day=hoy, total_tokens=999, requests=1)

    r = client.post("/v1/chat/completions", json=cuerpo_chat, headers=auth)
    assert r.status_code == 429
    assert r.json()["error"]["type"] == "insufficient_quota"
    assert int(r.headers["Retry-After"]) > 60
