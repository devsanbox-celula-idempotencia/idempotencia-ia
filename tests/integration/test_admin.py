"""Endpoints de /admin: claves, consumo y logs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.entities.request_log import RequestLog
from app.domain.entities.usage import Usage


# --------------------------------------------------------------------- acceso
def test_sin_token_de_admin_devuelve_403(client) -> None:
    for metodo, ruta in (
        ("get", "/admin/api-keys?user_id=1"),
        ("post", "/admin/api-keys"),
        ("get", "/admin/usage?start=2026-01-01&end=2026-12-31"),
        ("get", "/admin/logs"),
    ):
        r = client.request(metodo.upper(), ruta, json={} if metodo == "post" else None)
        assert r.status_code == 403, ruta


def test_token_de_admin_incorrecto_devuelve_403(client) -> None:
    r = client.get("/admin/logs", headers={"X-Admin-Token": "otro"})
    assert r.status_code == 403


def test_la_api_key_no_sirve_para_admin(client, auth) -> None:
    assert client.get("/admin/logs", headers=auth).status_code == 403


# --------------------------------------------------------------------- crear claves
def test_crear_clave(client, admin, uow) -> None:
    r = client.post(
        "/admin/api-keys",
        json={"user_id": 1, "name": "cliente-web", "requests_per_minute": 30},
        headers=admin,
    )
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["api_key"].startswith("sk_live_")
    assert cuerpo["name"] == "cliente-web"

    creada = uow.api_keys.items[cuerpo["id"]]
    assert creada.key_hash != cuerpo["api_key"]      # nunca en claro
    assert len(creada.key_hash) == 64                # SHA-256 en hexadecimal
    assert cuerpo["api_key"].startswith(creada.key_prefix)
    assert creada.requests_per_minute == 30


def test_crear_clave_para_usuario_inexistente(client, admin) -> None:
    r = client.post("/admin/api-keys", json={"user_id": 999, "name": "x"}, headers=admin)
    assert r.status_code == 400
    assert "999" in r.json()["error"]["message"]


def test_expires_at_con_zona_horaria_se_normaliza_a_utc(client, admin, uow) -> None:
    """DATETIME2 no guarda offset: sin normalizar, la clave caducaría con horas
    de diferencia."""
    r = client.post(
        "/admin/api-keys",
        json={"user_id": 1, "name": "x", "expires_at": "2026-09-01T00:00:00-05:00"},
        headers=admin,
    )
    assert r.status_code == 201
    creada = uow.api_keys.items[r.json()["id"]]
    assert creada.expires_at == datetime(2026, 9, 1, 5, 0, 0)
    assert creada.expires_at.tzinfo is None


def test_validaciones_al_crear(client, admin) -> None:
    for caso in (
        {"user_id": 1},                                     # falta name
        {"name": "x"},                                      # falta user_id
        {"user_id": 1, "name": "x" * 200},                  # name > 100
        {"user_id": 1, "name": "x", "requests_per_minute": 0},
        {"user_id": 1, "name": "x", "daily_token_limit": -5},
        {"user_id": "uno", "name": "x"},
    ):
        assert client.post("/admin/api-keys", json=caso, headers=admin).status_code == 422, caso


# --------------------------------------------------------------------- listar y revocar
def test_listar_claves_de_un_usuario(client, admin) -> None:
    cuerpo = client.get("/admin/api-keys?user_id=1", headers=admin).json()
    assert {c["name"] for c in cuerpo} == {"valida", "revocada", "expirada"}
    assert all("api_key" not in c for c in cuerpo)    # nunca se devuelve la clave


def test_listar_usuario_sin_claves(client, admin) -> None:
    assert client.get("/admin/api-keys?user_id=99", headers=admin).json() == []


def test_revocar_clave(client, admin, uow) -> None:
    r = client.delete("/admin/api-keys/1", headers=admin)
    assert r.status_code == 204
    assert r.content == b""
    assert uow.api_keys.items[1].is_active is False


def test_revocar_clave_inexistente(client, admin) -> None:
    assert client.delete("/admin/api-keys/999", headers=admin).status_code == 400


def test_una_clave_revocada_deja_de_servir(client, admin, auth) -> None:
    assert client.get("/v1/models", headers=auth).status_code == 200
    client.delete("/admin/api-keys/1", headers=admin)
    assert client.get("/v1/models", headers=auth).status_code == 401


# --------------------------------------------------------------------- consumo
def test_consumo_agregado_y_por_dia(client, admin, uow) -> None:
    hoy = datetime.now(timezone.utc).date()
    ayer = hoy - timedelta(days=1)
    uow.usage.items[(1, ayer)] = Usage(
        api_key_id=1, day=ayer, prompt_tokens=10, completion_tokens=20, total_tokens=30, requests=2
    )
    uow.usage.items[(1, hoy)] = Usage(
        api_key_id=1, day=hoy, prompt_tokens=5, completion_tokens=5, total_tokens=10, requests=1
    )

    cuerpo = client.get(
        f"/admin/usage?start={ayer}&end={hoy}&api_key_id=1", headers=admin
    ).json()
    assert cuerpo["total_requests"] == 3
    assert cuerpo["total_tokens"] == 40
    assert [d["day"] for d in cuerpo["days"]] == [str(ayer), str(hoy)]


def test_consumo_sin_filtrar_por_clave(client, admin, uow) -> None:
    hoy = datetime.now(timezone.utc).date()
    uow.usage.items[(1, hoy)] = Usage(api_key_id=1, day=hoy, total_tokens=10, requests=1)
    uow.usage.items[(2, hoy)] = Usage(api_key_id=2, day=hoy, total_tokens=7, requests=1)
    cuerpo = client.get(f"/admin/usage?start={hoy}&end={hoy}", headers=admin).json()
    assert cuerpo["total_tokens"] == 17
    assert cuerpo["api_key_id"] is None


def test_consumo_rango_vacio(client, admin) -> None:
    cuerpo = client.get("/admin/usage?start=2020-01-01&end=2020-01-02", headers=admin).json()
    assert cuerpo["total_tokens"] == 0
    assert cuerpo["days"] == []


def test_consumo_fechas_invalidas(client, admin) -> None:
    assert client.get("/admin/usage?start=ayer&end=hoy", headers=admin).status_code == 422
    assert client.get("/admin/usage", headers=admin).status_code == 422


# --------------------------------------------------------------------- logs
def _sembrar_logs(uow, cantidad: int) -> None:
    base = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(cantidad):
        uow.logs.items.append(
            RequestLog(
                api_key_id=1,
                model="qwen2.5:3b",
                endpoint="/v1/chat/completions",
                total_tokens=i,
                status_code=200,
                created_at=base - timedelta(seconds=i),
                id=i + 1,
            )
        )


def test_listar_logs(client, admin, uow) -> None:
    _sembrar_logs(uow, 5)
    cuerpo = client.get("/admin/logs", headers=admin).json()
    assert len(cuerpo) == 5
    assert cuerpo[0]["model"] == "qwen2.5:3b"


def test_logs_paginacion(client, admin, uow) -> None:
    _sembrar_logs(uow, 10)
    pagina1 = client.get("/admin/logs?limit=3&offset=0", headers=admin).json()
    pagina2 = client.get("/admin/logs?limit=3&offset=3", headers=admin).json()
    assert len(pagina1) == len(pagina2) == 3
    assert {x["id"] for x in pagina1}.isdisjoint({x["id"] for x in pagina2})


def test_logs_limites_invalidos_devuelven_422(client, admin) -> None:
    """Regresión: SQL Server rechaza FETCH con 0 filas y OFFSET negativo, así
    que sin estas cotas salía un 500."""
    for consulta in ("limit=0", "limit=-1", "limit=5000", "offset=-1"):
        r = client.get(f"/admin/logs?{consulta}", headers=admin)
        assert r.status_code == 422, consulta


def test_logs_filtro_por_clave(client, admin, uow) -> None:
    _sembrar_logs(uow, 3)
    uow.logs.items.append(
        RequestLog(api_key_id=2, model="m", endpoint="/x", created_at=datetime(2026, 1, 1), id=99)
    )
    cuerpo = client.get("/admin/logs?api_key_id=2", headers=admin).json()
    assert [x["id"] for x in cuerpo] == [99]


def test_logs_filtro_por_fechas_con_zona_horaria(client, admin, uow) -> None:
    """El filtro debe normalizarse a UTC naive, como la columna.

    Ventana estrecha a propósito: con un `since` de hace años el test pasaría
    aunque hubiera un desfase de cinco horas.
    """
    _sembrar_logs(uow, 3)
    # El mismo instante (hace un minuto) expresado en UTC-5. Sin normalizar, el
    # filtro se desplazaría 5 horas hacia el futuro y no devolvería nada.
    since = (
        (datetime.now(timezone.utc) - timedelta(minutes=1))
        .astimezone(timezone(timedelta(hours=-5)))
        .isoformat()
    )
    r = client.get(f"/admin/logs?since={since}", headers=admin)
    assert r.status_code == 200
    assert len(r.json()) == 3
