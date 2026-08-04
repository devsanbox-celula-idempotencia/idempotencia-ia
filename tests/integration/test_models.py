"""GET /v1/models y GET /v1/models/{id}."""
from __future__ import annotations

from app.domain.entities.model import LLMModel


def test_listar_modelos_desde_el_catalogo(client, auth) -> None:
    cuerpo = client.get("/v1/models", headers=auth).json()
    assert cuerpo["object"] == "list"
    assert [m["id"] for m in cuerpo["data"]] == ["qwen2.5:3b"]
    assert cuerpo["data"][0]["object"] == "model"


def test_catalogo_vacio_cae_en_allowed_models(client, auth, uow) -> None:
    uow.models.items = []
    cuerpo = client.get("/v1/models", headers=auth).json()
    assert [m["id"] for m in cuerpo["data"]] == ["qwen2.5:3b"]


def test_modelo_inactivo_no_se_lista(client, auth, uow) -> None:
    uow.models.items = [
        LLMModel(id="viejo", provider_model="viejo", is_active=False),
        LLMModel(id="qwen2.5:3b", provider_model="qwen2.5:3b"),
    ]
    ids = [m["id"] for m in client.get("/v1/models", headers=auth).json()["data"]]
    assert "viejo" not in ids


def test_obtener_un_modelo(client, auth) -> None:
    cuerpo = client.get("/v1/models/qwen2.5:3b", headers=auth).json()
    assert cuerpo["id"] == "qwen2.5:3b"
    assert cuerpo["object"] == "model"


def test_modelo_desconocido_devuelve_404(client, auth) -> None:
    r = client.get("/v1/models/llama3:70b", headers=auth)
    assert r.status_code == 404
    assert r.json()["error"]["type"] == "model_not_found"


def test_created_se_calcula_en_utc(client, auth) -> None:
    """created_at llega naive desde SQL Server pero es UTC: 2026-01-01 = 1767225600."""
    cuerpo = client.get("/v1/models", headers=auth).json()
    assert cuerpo["data"][0]["created"] == 1767225600
