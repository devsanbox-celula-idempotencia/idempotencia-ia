"""POST /v1/completions (API legacy de OpenAI)."""
from __future__ import annotations


def test_camino_feliz(client, auth) -> None:
    r = client.post(
        "/v1/completions",
        json={"model": "qwen2.5:3b", "prompt": "El cielo es", "max_tokens": 20},
        headers=auth,
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["object"] == "text_completion"
    assert cuerpo["choices"][0]["text"] == "Hola desde el modelo"
    assert cuerpo["usage"]["total_tokens"] == 15


def test_prompt_como_lista_se_une(client, auth, provider) -> None:
    client.post(
        "/v1/completions",
        json={"model": "qwen2.5:3b", "prompt": ["linea uno", "linea dos"]},
        headers=auth,
    )
    assert provider.llamadas[0]["messages"] == [
        {"role": "user", "content": "linea uno\nlinea dos"}
    ]


def test_stop_se_pasa_al_modelo(client, auth, provider) -> None:
    """Regresión: este endpoint descartaba `stop` en silencio."""
    client.post(
        "/v1/completions",
        json={"model": "qwen2.5:3b", "prompt": "x", "stop": "FIN"},
        headers=auth,
    )
    assert provider.llamadas[0]["options"]["stop"] == ["FIN"]


def test_streaming_no_soportado_devuelve_400(client, auth) -> None:
    r = client.post(
        "/v1/completions",
        json={"model": "qwen2.5:3b", "prompt": "x", "stream": True},
        headers=auth,
    )
    assert r.status_code == 400
    assert "chat/completions" in r.json()["error"]["message"]


def test_n_mayor_que_uno_devuelve_400(client, auth) -> None:
    r = client.post(
        "/v1/completions", json={"model": "qwen2.5:3b", "prompt": "x", "n": 2}, headers=auth
    )
    assert r.status_code == 400


def test_valores_numericos_invalidos(client, auth) -> None:
    for caso in (
        {"model": "qwen2.5:3b", "prompt": "x", "temperature": 5},
        {"model": "qwen2.5:3b", "prompt": "x", "top_p": -1},
        {"model": "qwen2.5:3b", "prompt": "x", "max_tokens": -2},
    ):
        assert client.post("/v1/completions", json=caso, headers=auth).status_code == 422, caso


def test_nan_no_provoca_un_500(client, auth) -> None:
    """NaN es JSON no estándar pero json.loads lo acepta; antes llegaba a httpx
    y reventaba con un 500."""
    r = client.post(
        "/v1/completions",
        content=b'{"model":"qwen2.5:3b","prompt":"x","temperature":NaN}',
        headers={**auth, "Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_sin_autenticacion(client) -> None:
    assert client.post("/v1/completions", json={"model": "m", "prompt": "x"}).status_code == 401


def test_registra_consumo(client, auth, uow) -> None:
    client.post("/v1/completions", json={"model": "qwen2.5:3b", "prompt": "x"}, headers=auth)
    assert uow.logs.items[0].endpoint == "/v1/completions"
    assert uow.logs.items[0].total_tokens == 15
