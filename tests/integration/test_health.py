"""GET /health y GET /ready."""
from __future__ import annotations

from tests.fakes import FakeSession


def test_health_no_requiere_autenticacion(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_ok_con_todo_arriba(client) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["status"] == "ok"
    assert cuerpo["database"] is True
    assert cuerpo["ollama"] is True


def test_ready_degradado_si_ollama_no_responde(client, provider) -> None:
    provider.sano = False
    cuerpo = client.get("/ready").json()
    assert cuerpo["status"] == "degraded"
    assert cuerpo["ollama"] is False
    assert cuerpo["database"] is True


def test_ready_degradado_y_con_detalle_si_falla_la_base(client, session: FakeSession) -> None:
    session.fallo = RuntimeError("login failed")
    cuerpo = client.get("/ready").json()
    assert cuerpo["status"] == "degraded"
    assert cuerpo["database"] is False
    # Con DEBUG=true se expone el error concreto: sin esto solo se veía "false"
    assert "login failed" in cuerpo["database_error"]


def test_openapi_expone_todos_los_endpoints(client) -> None:
    rutas = client.get("/openapi.json").json()["paths"]
    for esperada in (
        "/v1/chat/completions",
        "/v1/completions",
        "/v1/models",
        "/v1/embeddings",
        "/admin/api-keys",
        "/admin/usage",
        "/admin/logs",
        "/health",
        "/ready",
    ):
        assert esperada in rutas, esperada


def test_cabeceras_de_traza(client) -> None:
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")
    assert r.headers.get("X-Response-Time-Ms") is not None


def test_request_id_se_respeta_si_lo_manda_el_cliente(client) -> None:
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
