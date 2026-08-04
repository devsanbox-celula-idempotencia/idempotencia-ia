# Pruebas

## Ejecutar

```bash
pip install --only-binary=:all: -r requirements-dev.txt
pytest -q                        # toda la suite
pytest -v                        # con el nombre de cada caso
pytest --cov=app --cov-report=term-missing
```

**No hace falta SQL Server ni Ollama.** Los casos de uso dependen de puertos
(interfaces), así que las pruebas inyectan dobles en memoria definidos en
`tests/fakes.py`. Esa es la ventaja concreta de la arquitectura: ejercitar los
endpoints completos sin levantar infraestructura.

## Cómo está montado

```
tests/
├── fakes.py                    Dobles de los puertos: repositorios en memoria,
│                               FakeLLMProvider, FakeUsageRecorder, FakeContainer
├── conftest.py                 Fixtures: la app con TODAS las dependencias
│                               sustituidas + claves de prueba
├── unit/                       Sin HTTP
│   ├── test_domain.py          Entidades y reglas de negocio
│   ├── test_openai_mapper.py   Traducción OpenAI ↔ Ollama
│   ├── test_record_usage.py    Las dos fases del registro de consumo
│   ├── test_security.py        Hash y generación de claves
│   ├── test_rate_limiter.py    Limitador en memoria
│   └── test_ollama_provider.py Protocolo real de Ollama, con respx
├── integration/                Endpoints completos vía TestClient
│   ├── test_health.py
│   ├── test_auth.py
│   ├── test_models.py
│   ├── test_chat_completions.py
│   ├── test_completions.py
│   ├── test_embeddings.py
│   ├── test_admin.py
│   └── test_limites_y_seguridad.py
└── e2e/
    └── test_sdk_real.py        Contra un despliegue real; se salta por defecto
```

La sustitución de dependencias se hace en `tests/conftest.py`:

| Dependencia real | Doble |
|---|---|
| `get_uow` | `FakeUnitOfWork` con repositorios en memoria |
| `get_provider` / `get_container` | `FakeLLMProvider` determinista |
| `get_usage_recorder` | `FakeUsageRecorder` (misma lógica, sin base de datos) |
| `get_session` | `FakeSession` (solo para `/ready`) |
| `get_settings` | `Settings` aislados con `_env_file=None` |

Ese `_env_file=None` importa: sin él, el `.env` de la máquina donde se ejecuta
la suite se colaría en las pruebas y bastaría con vaciar `OPENAPI_URL` para que
fallaran.

## Cobertura por endpoint

| Endpoint | Casos cubiertos |
|---|---|
| `POST /v1/chat/completions` | 200 con formato OpenAI · registro de consumo y log · orden del cierre de conexión · traducción de parámetros a `options` · `stop` vacío descartado · `temperature: 0` · `finish_reason: length` · streaming (SSE, rol, último chunk, `[DONE]`, consumo) · 400 `n>1` · 404 modelo · 401 · 422 (7 casos) · 429 RPM · 429 cuota · 500 inesperado · 502 backend · `X-Forwarded-For` falsificado |
| `POST /v1/completions` | 200 · `prompt` como lista · `stop` propagado · penalizaciones propagadas · 400 `stream` · 400 `n>1` · 422 rangos · 422 `NaN` · 401 · registro |
| `GET /v1/models` | catálogo · respaldo a `ALLOWED_MODELS` · inactivos ocultos · `created` en UTC · 401 · 429 |
| `GET /v1/models/{id}` | 200 · 404 · id con `/` |
| `POST /v1/embeddings` | lista · texto suelto · 422 (vacío, lista vacía, >512, elemento vacío) · 502 · 404 · 401 · registro |
| `POST /admin/api-keys` | 201 y hash guardado · la clave sirve · 400 usuario inexistente · `expires_at` con zona horaria · 422 (6 casos) · 403 |
| `GET /admin/api-keys` | listado · vacío · nunca devuelve la clave · 403 |
| `DELETE /admin/api-keys/{id}` | 204 · 400 inexistente · la clave revocada deja de servir |
| `GET /admin/usage` | agregado y por día · sin filtro · rango vacío · 422 fechas · 403 |
| `GET /admin/logs` | listado · paginación · filtro por clave · filtro con zona horaria · 422 `limit`/`offset` · 403 |
| `GET /health` | 200 sin autenticación · cabeceras de traza |
| `GET /ready` | ok · degradado por Ollama · degradado por base de datos · no filtra detalles con `DEBUG=false` |

Además: token de administración con caracteres no ASCII, ruta inexistente,
método no permitido, y el limitador desactivado.

## Regresiones fijadas

Cada uno de estos tests existe porque el bug ocurrió de verdad:

| Test | Bug que evita |
|---|---|
| `test_suelta_la_conexion_antes_de_llamar_al_modelo` | Se retenía la conexión durante los 35 s de inferencia y SQL Server la cerraba → `08S01` y un 500 tras haber gastado los tokens |
| `test_x_forwarded_for_basura_no_rompe_la_peticion` | Un `X-Forwarded-For` largo desbordaba `ClientIp NVARCHAR(45)`, se perdía todo el registro y se podía consumir gratis sin dejar rastro |
| `TestRequestLogRecorta::test_error_en_unidades_utf16` | `texto[:1000]` no basta: `NVARCHAR` cuenta unidades UTF-16 y un emoji ocupa 2 |
| `test_las_fases_son_independientes` y `test_reintentar_solo_la_fase_del_log_no_cobra_dos_veces` | Reintentar el registro completo volvía a aplicar un incremento ya confirmado: doble cobro |
| `test_logs_limites_invalidos_devuelven_422` | SQL Server rechaza `FETCH` con 0 filas y `OFFSET` negativo → 500 en vez de 422 |
| `test_nan_no_provoca_un_500` | `NaN` llegaba hasta httpx y reventaba |
| `test_stop_vacio_no_llega_al_modelo` | Una secuencia de parada vacía cortaba la generación en el token 0 y se facturaba una respuesta vacía |
| `test_stop_escalar_largo_es_valido` | `max_length=4` sobre `list[str] \| str` limitaba la CADENA a 4 caracteres |
| `test_streaming_rol_aunque_el_primer_chunk_venga_vacio` | Se perdía `delta.role`, que el contrato de OpenAI exige en el primer chunk |
| `test_finish_reason_length_se_propaga` | Siempre se devolvía `"stop"`: el cliente no distinguía una respuesta truncada |
| `test_token_de_admin_con_caracteres_no_ascii_devuelve_403` | `compare_digest` sobre `str` no-ASCII lanza `TypeError` → 500 |
| `test_ready_no_filtra_detalles_con_debug_apagado` | El detalle del error de base de datos incluye host y usuario |
| `test_logs_filtro_por_fechas_con_zona_horaria` | `DATETIME2` no guarda offset y pyodbc ignora el `tzinfo`: la ventana se desplazaba |
| `test_todos_los_endpoints_v1_respetan_el_limite` | `/v1/models` se quedó sin limitador |
| `test_completions_propaga_las_penalizaciones` | `/v1/completions` las validaba y luego las descartaba |

## Pruebas de extremo a extremo

`tests/e2e/test_sdk_real.py` usa el SDK oficial de OpenAI contra un despliegue
real. Se salta salvo que se definan las variables:

```bash
GATEWAY_URL=http://localhost:8000 GATEWAY_KEY=sk_live_... pytest tests/e2e -v
```

Es la única prueba que valida de verdad la premisa del proyecto: que el SDK
oficial funcione cambiando solo `base_url`.

## Lo que deliberadamente NO se prueba aquí

- **Los repositorios SQLAlchemy y el `MERGE`**: requieren un SQL Server real.
  El dialecto es específico (`MERGE ... WITH (HOLDLOCK)`, `= 1` en vez de
  `IS TRUE`), así que una prueba contra SQLite daría una falsa sensación de
  seguridad. Se validan con `python -m scripts.check_db` y con los e2e.
- **`RedisRateLimiter`**: necesita Redis. La lógica de ventana está cubierta por
  el equivalente en memoria.
- **La cancelación del cliente a mitad de stream** (el `CancelScope(shield=True)`):
  no es reproducible con `TestClient`, que consume el cuerpo entero.

## Añadir un test

Para un endpoint nuevo, casi siempre basta con:

```python
def test_lo_que_sea(client, auth, uow, provider):
    r = client.post("/v1/lo-que-sea", json={...}, headers=auth)
    assert r.status_code == 200
    assert uow.logs.items[0].total_tokens == 15      # ¿quedó auditado?
```

`provider.fallo = ProviderError("...")` simula que Ollama no responde, y
`provider.chunks = [...]` controla exactamente qué emite el streaming.
