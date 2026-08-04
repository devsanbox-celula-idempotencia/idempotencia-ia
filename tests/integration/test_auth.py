"""Autenticación por API key: se prueba sobre /v1/models, que la exige igual."""
from __future__ import annotations

from tests.conftest import CLAVE_EXPIRADA, CLAVE_REVOCADA, CLAVE_VALIDA


def test_sin_cabecera_authorization_devuelve_401(client) -> None:
    r = client.get("/v1/models")
    assert r.status_code == 401
    assert r.json()["error"]["type"] == "invalid_request_error"


def test_esquema_incorrecto_devuelve_401(client) -> None:
    assert client.get("/v1/models", headers={"Authorization": "Basic abc"}).status_code == 401


def test_bearer_vacio_devuelve_401(client) -> None:
    assert client.get("/v1/models", headers={"Authorization": "Bearer "}).status_code == 401


def test_clave_inexistente_devuelve_401(client) -> None:
    r = client.get("/v1/models", headers={"Authorization": "Bearer sk_live_noexiste"})
    assert r.status_code == 401
    assert "inválida" in r.json()["error"]["message"]


def test_clave_revocada_devuelve_401(client) -> None:
    r = client.get("/v1/models", headers={"Authorization": f"Bearer {CLAVE_REVOCADA}"})
    assert r.status_code == 401
    assert "inactiva" in r.json()["error"]["message"]


def test_clave_expirada_devuelve_401(client) -> None:
    r = client.get("/v1/models", headers={"Authorization": f"Bearer {CLAVE_EXPIRADA}"})
    assert r.status_code == 401


def test_clave_valida_pasa_y_marca_el_ultimo_uso(client, uow) -> None:
    r = client.get("/v1/models", headers={"Authorization": f"Bearer {CLAVE_VALIDA}"})
    assert r.status_code == 200
    assert uow.api_keys.touched == [1]


def test_la_clave_en_claro_nunca_se_guarda(client, uow) -> None:
    """Se crea una clave por la API y se comprueba qué quedó realmente guardado."""
    from hashlib import sha256

    from tests.conftest import ADMIN_TOKEN

    respuesta = client.post(
        "/admin/api-keys",
        json={"user_id": 1, "name": "prueba"},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    ).json()
    en_claro = respuesta["api_key"]
    guardada = uow.api_keys.items[respuesta["id"]]

    assert en_claro not in guardada.key_hash
    assert guardada.key_hash == sha256(en_claro.encode()).hexdigest()

    # Y esa clave recién creada sirve de verdad para autenticarse
    r = client.get("/v1/models", headers={"Authorization": f"Bearer {en_claro}"})
    assert r.status_code == 200
