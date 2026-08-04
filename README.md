# Ollama Gateway — API compatible con OpenAI

API en FastAPI que expone un backend de Ollama (`qwen2.5:3b`) con el **mismo contrato que la API de OpenAI**,
añadiendo autenticación por API key, límites de uso, conteo de tokens y auditoría.

El cliente nunca habla con Ollama: habla con este gateway. Eso permite cambiar el motor
(Ollama → vLLM → OpenAI → Anthropic) sin tocar a los consumidores.

```
Cliente (SDK de OpenAI)
        │
        ▼
   /v1/chat/completions          FastAPI
        │
  API Key ─ Rate Limit ─ Logging ─ Token Counter
        │
   SQL Server (+ Redis opcional)
        │
        ▼
   Ollama  http://localhost:11434  →  qwen2.5:3b
```

## Puesta en marcha en 5 pasos

### 1. Instalar Ollama y el modelo

Descarga Ollama desde <https://ollama.com/download> y luego:

```bash
ollama pull qwen2.5:3b
ollama serve
```

Verifica: `curl http://localhost:11434/api/tags` debe listar `qwen2.5:3b`.

### 2. Crear las tablas

Abre `scripts/sql/001_create_tables.sql` en SSMS (o Azure Data Studio) contra tu base de datos
y ejecútalo. Crea 4 tablas nuevas y reutiliza tu tabla `Users` existente:

| Tabla | Para qué |
|---|---|
| `ApiKeys` | Claves `sk_live_...` de tus clientes (solo el hash) |
| `ApiKeyUsage` | Consumo acumulado por clave y día |
| `RequestLogs` | Una fila por petición: modelo, tokens, latencia, estado |
| `LlmModels` | Catálogo de modelos que expone el gateway |

### 3. Configurar la conexión

Edita `.env` y ajusta **una sola línea**:

```env
DATABASE_URL=mssql+aioodbc://usuario:password@localhost:1433/TU_BASE?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
```

Necesitas el **ODBC Driver 18 for SQL Server** instalado en el sistema
(<https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server>).

### 4. Instalar dependencias y levantar

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install --only-binary=:all: -r requirements.txt

uvicorn app.main:app --reload
```

> `--only-binary=:all:` obliga a pip a usar paquetes precompilados. Sin esa opción,
> si tu versión de Python es más nueva que las ruedas disponibles, pip intenta compilar
> `pydantic-core` (Rust) y `pyodbc` (C) desde el código fuente y falla pidiendo
> Visual Studio Build Tools. Si aun así falla, usa Python 3.12 o 3.13 para el entorno virtual.

Swagger: <http://localhost:8000/docs> — el botón **Authorize** pide tu `sk_live_...`.

### 5. Crear tu primera API key

Necesitas un `UserId` que ya exista en tu tabla `Users`:

```bash
python -m scripts.create_admin_key --user-id 1 --name "clave inicial" --rpm 60
```

Imprime la clave **una sola vez**. En la base de datos solo queda su SHA-256.

## Uso desde el SDK de OpenAI

```python
from openai import OpenAI

client = OpenAI(api_key="sk_live_xxx", base_url="http://localhost:8000/v1")

resp = client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Hola"}],
)
print(resp.choices[0].message.content)
print(resp.usage)          # prompt_tokens / completion_tokens / total_tokens
```

Streaming:

```python
for chunk in client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Cuéntame un chiste"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

## Endpoints

**Compatibles con OpenAI** — `Authorization: Bearer sk_live_...`

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/v1/chat/completions` | Chat, con o sin `stream` |
| POST | `/v1/completions` | Completions (legacy) |
| GET | `/v1/models` | Modelos disponibles |
| GET | `/v1/models/{id}` | Detalle de un modelo |
| POST | `/v1/embeddings` | Embeddings |

**Administración** — `X-Admin-Token: <ADMIN_TOKEN del .env>`

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/admin/api-keys` | Crear key |
| GET | `/admin/api-keys?user_id=1` | Listar keys de un usuario |
| DELETE | `/admin/api-keys/{id}` | Revocar |
| GET | `/admin/usage?start=&end=` | Consumo por rango |
| GET | `/admin/logs` | Historial de peticiones |
| GET | `/health`, `/ready` | Liveness y readiness |

## Stack

| Pieza | Tecnología |
|---|---|
| API | FastAPI + Uvicorn |
| Validación | Pydantic v2 |
| Persistencia | SQL Server + SQLAlchemy 2.0 async (`aioodbc`) |
| Rate limiting | En memoria por defecto; Redis con `RATE_LIMIT_BACKEND=redis` |
| Cliente HTTP | httpx (async) |
| Docs | Swagger UI (`/docs`) y ReDoc (`/redoc`) |

## Estructura (Clean Architecture)

Regla de dependencias: **domain ← application ← infrastructure / presentation**.
El dominio no importa nada de FastAPI, SQLAlchemy ni httpx.

```
app/
├── domain/                     # Núcleo: reglas de negocio puras
│   ├── entities/               # User, ApiKey, Usage, RequestLog, LLMModel
│   ├── value_objects/          # TokenUsage, RateLimitPolicy
│   ├── ports/
│   │   ├── repositories/       # Interfaces de persistencia
│   │   └── services/           # LLMProvider, RateLimiter, TokenCounter, UnitOfWork
│   └── exceptions.py
│
├── application/                # Casos de uso
│   ├── dto/
│   └── use_cases/
│       ├── auth/               # AuthenticateApiKey, CheckRateLimit
│       ├── chat/               # CreateChatCompletion, StreamChatCompletion
│       ├── models/             # ListModels, ResolveModel
│       ├── embeddings/         # CreateEmbeddings
│       └── admin/              # Keys, usage, logs, RecordUsage
│
├── infrastructure/             # Implementaciones concretas
│   ├── config/                 # Settings (.env) y Container (composition root)
│   ├── db/                     # Sesión, modelos ORM, mappers, UnitOfWork
│   ├── repositories/           # Repositorios SQLAlchemy
│   ├── llm/                    # OllamaClient, OllamaProvider, openai_mapper
│   ├── cache/                  # Rate limiters (memoria / Redis)
│   ├── security/               # SHA-256 y generación de keys
│   ├── tokenizer/              # Conteo de tokens
│   └── observability/          # Logging
│
└── presentation/               # Entrada HTTP
    ├── api/v1/                 # Endpoints compatibles con OpenAI
    ├── api/admin/              # Endpoints internos + health
    ├── schemas/                # Pydantic: openai/ y admin/
    ├── middleware/             # request-id, logging, errores
    ├── dependencies.py         # Auth Bearer, rate limit, admin token
    └── openapi.py              # Personalización de Swagger
```

## Flujo de una petición

```
Cliente → Bearer sk_live_... → SHA-256 → buscar en ApiKeys → validar activa/no expirada
       → rate limit (RPM) + cuota de tokens del día
       → resolver modelo contra LlmModels
       → POST http://localhost:11434/api/chat
       → tokens desde prompt_eval_count / eval_count
       → acumular en ApiKeyUsage + insertar en RequestLogs
       → responder en formato OpenAI
```

## Detalles de implementación que conviene conocer

- **El catálogo es opcional al inicio.** Si `LlmModels` está vacía, se aceptan los modelos
  listados en `ALLOWED_MODELS` del `.env`. Cualquier otro nombre devuelve `model_not_found`:
  así nadie puede pedirle a tu servidor que cargue un modelo de 70B.
- **Streaming y sesión de base de datos.** FastAPI cierra las dependencias `yield` antes de que
  termine de consumirse el cuerpo del stream. Por eso el registro del consumo en streaming usa
  `ScopedRecordUsage`, que abre su propia sesión (`app/infrastructure/db/scoped_record_usage.py`).
- **Middlewares ASGI puros.** `RequestIdMiddleware` y `LoggingMiddleware` no usan
  `BaseHTTPMiddleware` para no interferir con las respuestas SSE.
- **Errores en formato OpenAI.** Las excepciones de dominio se traducen a
  `{"error": {"message": ..., "type": ...}}` con el código HTTP correcto.
- **Un fallo de auditoría nunca rompe la respuesta** al cliente en streaming.
- **La conexión a la base de datos se suelta antes de llamar al modelo**
  (`await uow.close()` en los routers de `/v1`). Una respuesta puede tardar
  decenas de segundos; mantener la conexión ocupada hace que el servidor la
  cierre por inactividad y el registro posterior falle con `08S01`.
- **Todas las fechas son UTC.** `RequestLogs.CreatedAt` lo pone `SYSUTCDATETIME()`
  y el día de `ApiKeyUsage` se calcula con `datetime.now(timezone.utc).date()`.
  Usar `date.today()` (hora local) descuadraría el consumo respecto a los logs.
- **`RequestLog` recorta sus propios campos.** SQL Server no trunca: aborta el
  INSERT. Como el fallo de auditoría se traga para no romper la respuesta, un
  `X-Forwarded-For` largo habría permitido consumir sin quedar registrado.
  El recorte cuenta unidades UTF-16, que es como mide `NVARCHAR`.

## Limitaciones conocidas

- **La cuota diaria de tokens se comprueba antes de llamar al modelo y se
  contabiliza después.** Con peticiones concurrentes de la misma clave, el
  límite puede superarse por un margen igual a la concurrencia. Para un control
  estricto habría que reservar los tokens por adelantado y liberar el sobrante.
- **El limitador en memoria cuenta por proceso.** Con varios workers de uvicorn
  o varias instancias, cada uno lleva su propia cuenta: usa
  `RATE_LIMIT_BACKEND=redis`.
- **`n > 1` no está soportado** y `/v1/completions` no admite streaming; ambos
  devuelven 400 en vez de fingir la capacidad.

## Documentos

| Archivo | Para qué |
|---|---|
| `docs/api-endpoints.md` | Guía de los 10 endpoints con ejemplos |
| `docs/frontend-guide.md` | Integración desde una web: CORS, streaming, errores, tipos |
| `docs/runbook-devops.md` | Despliegue en VPS: systemd o Docker, Nginx, operación |
| `docs/testing.md` | Cómo está montada la suite y qué cubre |
| `docs/architecture.md` | Decisiones de arquitectura y por qué |
| `docs/deploy-vps.md` | Notas de dimensionamiento para un VPS de 4 GB |
| `scripts/sql/001_create_tables.sql` | Esquema para SQL Server |
| `scripts/sql/999_drop_tables.sql` | Deshacer el esquema |

## Pruebas

```bash
pip install --only-binary=:all: -r requirements-dev.txt
pytest -q
```

**No hace falta SQL Server ni Ollama**: los casos de uso dependen de puertos, así que las
pruebas inyectan dobles en memoria (`tests/fakes.py`). La suite cubre los 10 endpoints con
sus códigos de error, el streaming SSE, los límites y una regresión por cada bug que llegó
a producirse. Detalle en `docs/testing.md`.

Para probar contra un despliegue real con el SDK oficial de OpenAI:

```bash
GATEWAY_URL=http://localhost:8000 GATEWAY_KEY=sk_live_... pytest tests/e2e -v
```
