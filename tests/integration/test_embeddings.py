"""POST /v1/embeddings."""
from __future__ import annotations

from app.domain.exceptions import ProviderError


def test_lista_de_textos(client, auth) -> None:
    r = client.post(
        "/v1/embeddings",
        json={"model": "qwen2.5:3b", "input": ["hola", "mundo"]},
        headers=auth,
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["object"] == "list"
    assert [d["index"] for d in cuerpo["data"]] == [0, 1]
    assert cuerpo["data"][0]["embedding"] == [0.1, 0.2, 0.3]
    assert cuerpo["usage"]["prompt_tokens"] == 4


def test_texto_suelto(client, auth) -> None:
    cuerpo = client.post(
        "/v1/embeddings", json={"model": "qwen2.5:3b", "input": "hola"}, headers=auth
    ).json()
    assert len(cuerpo["data"]) == 1


def test_entradas_invalidas_devuelven_422(client, auth) -> None:
    """Antes salía un 502 culpando al backend de un error del cliente."""
    for entrada in ([], "", "   ", ["hola", ""], ["x"] * 513):
        r = client.post(
            "/v1/embeddings", json={"model": "qwen2.5:3b", "input": entrada}, headers=auth
        )
        assert r.status_code == 422, entrada


def test_error_del_backend_devuelve_502(client, auth, provider) -> None:
    provider.fallo = ProviderError("el modelo no soporta embeddings")
    r = client.post("/v1/embeddings", json={"model": "qwen2.5:3b", "input": "x"}, headers=auth)
    assert r.status_code == 502
    assert r.json()["error"]["type"] == "api_error"


def test_modelo_no_permitido(client, auth) -> None:
    r = client.post("/v1/embeddings", json={"model": "otro", "input": "x"}, headers=auth)
    assert r.status_code == 404


def test_sin_autenticacion(client) -> None:
    assert client.post("/v1/embeddings", json={"model": "m", "input": "x"}).status_code == 401


def test_registra_consumo(client, auth, uow) -> None:
    client.post("/v1/embeddings", json={"model": "qwen2.5:3b", "input": ["a", "b"]}, headers=auth)
    assert uow.logs.items[0].endpoint == "/v1/embeddings"
    assert uow.logs.items[0].total_tokens == 4
