# Guía de endpoints — Ollama Gateway

Base local: `http://localhost:8000`

Hay dos grupos con autenticación distinta:

| Grupo | Prefijo | Autenticación | Para quién |
|---|---|---|---|
| Compatible con OpenAI | `/v1` | `Authorization: Bearer sk_live_...` | Tus clientes |
| Administración | `/admin` | `X-Admin-Token: <ADMIN_TOKEN del .env>` | Tú |
| Salud | *(sin prefijo)* | Ninguna | Monitoreo |

Todas las respuestas llevan dos cabeceras útiles para depurar:

- `X-Request-ID` — el mismo identificador que aparece en los logs de uvicorn
- `X-Response-Time-Ms` — latencia total del gateway

---

# 1. Endpoints compatibles con OpenAI

Estos existen para que el SDK oficial funcione sin cambios. Si algo aquí no coincide
con la API de OpenAI, es un bug.

## POST /v1/chat/completions

El endpoint principal.

### Cuerpo de la petición

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `model` | string | sí | `qwen2.5:3b` |
| `messages` | array | sí | Objetos `{role, content}`. `role`: `system`, `user`, `assistant` o `tool` |
| `stream` | bool | no | `false` por defecto. Con `true` la respuesta es SSE |
| `temperature` | float 0–2 | no | Creatividad |
| `top_p` | float 0–1 | no | Muestreo por núcleo |
| `max_tokens` | int | no | Se traduce a `num_predict` de Ollama |
| `stop` | string o array | no | Secuencias de parada |
| `presence_penalty` | float | no | Se pasa a las options de Ollama |
| `frequency_penalty` | float | no | Idem |
| `n` | int | no | **Solo se acepta `1`**. Con más, devuelve 400 |
| `user` | string | no | Se acepta y se ignora |

### Ejemplo — sin streaming

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk_live_TU_CLAVE" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:3b",
    "messages": [
      {"role": "system", "content": "Responde en español, breve."},
      {"role": "user", "content": "¿Qué es una API REST?"}
    ],
    "temperature": 0.7,
    "max_tokens": 200
  }'
```

En PowerShell:

```powershell
$body = @{
    model    = "qwen2.5:3b"
    messages = @(@{ role = "user"; content = "¿Qué es una API REST?" })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/chat/completions `
    -Headers @{ Authorization = "Bearer sk_live_TU_CLAVE" } `
    -ContentType "application/json" -Body $body
```

### Respuesta

```json
{
  "id": "chatcmpl-4f3a9c2b8d1e6f0a7b2c3d4e",
  "object": "chat.completion",
  "created": 1785790000,
  "model": "qwen2.5:3b",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "Una API REST es..." },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 28,
    "completion_tokens": 142,
    "total_tokens": 170
  }
}
```

Ese bloque `usage` es el que se guarda en `ApiKeyUsage` y `RequestLogs`. Los números vienen
de `prompt_eval_count` y `eval_count`, que son los que Ollama reporta de verdad — no una
estimación.

### Ejemplo — con streaming

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk_live_TU_CLAVE" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:3b",
    "messages": [{"role": "user", "content": "Cuenta del 1 al 5"}],
    "stream": true
  }'
```

El `-N` desactiva el buffer de curl; sin él parece que no llega nada hasta el final.

La respuesta es `text/event-stream`, una línea por token:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":1785790000,"model":"qwen2.5:3b","choices":[{"index":0,"delta":{"role":"assistant","content":"1"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...,"choices":[{"index":0,"delta":{"content":", 2"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...,"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

Dos detalles del formato de OpenAI que el gateway respeta:

- Los chunks **no traen `usage`**. El consumo se guarda en base de datos al cerrar el stream.
- El último evento es literalmente `data: [DONE]`, no un JSON.

---

## POST /v1/completions

API antigua de OpenAI: un `prompt` plano en vez de mensajes. Internamente se traduce a un
chat de un solo mensaje de usuario.

```bash
curl -X POST http://localhost:8000/v1/completions \
  -H "Authorization: Bearer sk_live_TU_CLAVE" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:3b","prompt":"El cielo es","max_tokens":50}'
```

```json
{
  "id": "chatcmpl-...",
  "object": "text_completion",
  "created": 1785790000,
  "model": "qwen2.5:3b",
  "choices": [{ "index": 0, "text": " azul porque...", "finish_reason": "stop" }],
  "usage": { "prompt_tokens": 4, "completion_tokens": 12, "total_tokens": 16 }
}
```

Dos límites deliberados: `stream: true` devuelve **400** (usa `/v1/chat/completions`), y
`n > 1` también devuelve 400. Es preferible un error claro a fingir una capacidad que no está.

---

## GET /v1/models

```bash
curl http://localhost:8000/v1/models -H "Authorization: Bearer sk_live_TU_CLAVE"
```

```json
{
  "object": "list",
  "data": [
    { "id": "qwen2.5:3b", "object": "model", "created": 1785700000, "owned_by": "local" }
  ]
}
```

Sale de la tabla `LlmModels`. Si esa tabla está vacía, se devuelve lo que tengas en
`ALLOWED_MODELS` del `.env`.

## GET /v1/models/{id}

```bash
curl http://localhost:8000/v1/models/qwen2.5:3b -H "Authorization: Bearer sk_live_TU_CLAVE"
```

Devuelve un solo objeto `model`. Si el modelo no está habilitado: **404** `model_not_found`.

---

## POST /v1/embeddings

```bash
curl -X POST http://localhost:8000/v1/embeddings \
  -H "Authorization: Bearer sk_live_TU_CLAVE" \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text","input":["hola mundo","otro texto"]}'
```

`input` acepta un string o una lista de strings.

```json
{
  "object": "list",
  "data": [
    { "object": "embedding", "index": 0, "embedding": [0.021, -0.114, ...] },
    { "object": "embedding", "index": 1, "embedding": [0.007, 0.233, ...] }
  ],
  "model": "nomic-embed-text",
  "usage": { "prompt_tokens": 6, "completion_tokens": 0, "total_tokens": 6 }
}
```

**Ojo:** `qwen2.5:3b` es un modelo de chat, no de embeddings. Si lo usas aquí obtendrás un
502. Para que este endpoint sirva necesitas un modelo específico:

```bash
ollama pull nomic-embed-text
```

y añadirlo a `ALLOWED_MODELS` en el `.env`, o a la tabla `LlmModels` con
`SupportsEmbeddings = 1`.

---

# 2. Endpoints de administración

Todos requieren la cabecera `X-Admin-Token` con el valor de `ADMIN_TOKEN` de tu `.env`.
Sin ella o con un valor distinto: **403**.

## POST /admin/api-keys

Crea una clave para un usuario que ya exista en tu tabla `Users`.

```bash
curl -X POST http://localhost:8000/admin/api-keys \
  -H "X-Admin-Token: TU_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "name": "Integración web",
    "requests_per_minute": 30,
    "daily_token_limit": 100000
  }'
```

| Campo | Tipo | Obligatorio | Si lo omites |
|---|---|---|---|
| `user_id` | int | sí | — |
| `name` | string | sí | — |
| `expires_at` | datetime ISO | no | La clave no caduca |
| `requests_per_minute` | int | no | Se aplica `DEFAULT_REQUESTS_PER_MINUTE` |
| `daily_token_limit` | int | no | Se aplica `DEFAULT_TOKENS_PER_DAY` |
| `monthly_token_limit` | int | no | Sin límite mensual |

Respuesta **201**:

```json
{
  "id": 3,
  "name": "Integración web",
  "api_key": "sk_live_Yh2K9pQx7mZfR4tLvN8aB1cD6eG0sJwU",
  "created_at": "2026-08-03T21:14:07"
}
```

El campo `api_key` **solo aparece en esta respuesta**. En la base de datos queda su SHA-256
y un prefijo visible. Si el cliente la pierde, no se recupera: se revoca y se crea otra.

## GET /admin/api-keys?user_id=1

```bash
curl "http://localhost:8000/admin/api-keys?user_id=1" -H "X-Admin-Token: TU_ADMIN_TOKEN"
```

```json
[
  {
    "id": 3,
    "user_id": 1,
    "name": "Integración web",
    "key_prefix": "sk_live_Yh2",
    "is_active": true,
    "created_at": "2026-08-03T21:14:07",
    "last_used_at": "2026-08-03T21:20:33",
    "expires_at": null,
    "daily_token_limit": 100000,
    "requests_per_minute": 30
  }
]
```

`last_used_at` se actualiza en cada petición autenticada: sirve para detectar claves
olvidadas que conviene revocar.

## DELETE /admin/api-keys/{id}

```bash
curl -X DELETE http://localhost:8000/admin/api-keys/3 -H "X-Admin-Token: TU_ADMIN_TOKEN"
```

Responde **204** sin cuerpo. No borra la fila: pone `IsActive = 0`, para que los logs
históricos sigan apuntando a una clave que existe.

## GET /admin/usage

```bash
curl "http://localhost:8000/admin/usage?start=2026-08-01&end=2026-08-31&api_key_id=3" \
  -H "X-Admin-Token: TU_ADMIN_TOKEN"
```

| Parámetro | Obligatorio | Notas |
|---|---|---|
| `start` | sí | `YYYY-MM-DD` |
| `end` | sí | `YYYY-MM-DD`, inclusive |
| `api_key_id` | no | Sin él, agrega **todas** las claves |

```json
{
  "api_key_id": 3,
  "total_requests": 128,
  "prompt_tokens": 4120,
  "completion_tokens": 18740,
  "total_tokens": 22860,
  "days": [
    { "day": "2026-08-01", "requests": 40, "prompt_tokens": 1200,
      "completion_tokens": 5600, "total_tokens": 6800 }
  ]
}
```

Este es el endpoint sobre el que construirías un dashboard o la facturación.

## GET /admin/logs

```bash
curl "http://localhost:8000/admin/logs?limit=20" -H "X-Admin-Token: TU_ADMIN_TOKEN"
```

| Parámetro | Por defecto | Notas |
|---|---|---|
| `api_key_id` | — | Filtra por clave |
| `since` / `until` | — | Datetime ISO: `2026-08-01T00:00:00` |
| `limit` | 100 | Cuántas filas |
| `offset` | 0 | Para paginar |

```json
[
  {
    "id": 981,
    "api_key_id": 3,
    "model": "qwen2.5:3b",
    "endpoint": "/v1/chat/completions",
    "prompt_tokens": 28,
    "completion_tokens": 142,
    "total_tokens": 170,
    "duration_ms": 3480,
    "status_code": 200,
    "error": null,
    "created_at": "2026-08-03T21:20:33"
  }
]
```

Ordenado por fecha descendente. Para ver qué está fallando, filtra por `status_code` en SQL:

```sql
SELECT TOP 20 * FROM dbo.RequestLogs WHERE StatusCode <> 200 ORDER BY CreatedAt DESC;
```

---

# 3. Salud

## GET /health

Sin autenticación. Responde `{"status":"ok"}` si el proceso está vivo. Es lo que pondrías
en el health check de Docker o del balanceador.

## GET /ready

Comprueba las dependencias de verdad:

```json
{ "status": "ok", "database": true, "ollama": true }
```

Si algo falla, `status` pasa a `degraded`. Con `DEBUG=true` incluye además
`database_error` con el mensaje concreto y `database_url` sin la contraseña.

---

# 4. Errores

Todos siguen el formato de OpenAI, para que el SDK los interprete como errores nativos:

```json
{
  "error": {
    "message": "Límite de 30 peticiones por minuto superado. Reintenta en 42 s.",
    "type": "rate_limit_error",
    "param": null,
    "code": null
  }
}
```

| HTTP | `type` | Cuándo ocurre |
|---|---|---|
| 400 | `invalid_request_error` | `n > 1`, o `stream` en `/v1/completions` |
| 401 | `invalid_request_error` | Clave inexistente, revocada o expirada |
| 403 | `invalid_request_error` | `X-Admin-Token` incorrecto |
| 404 | `model_not_found` | El modelo no está en `LlmModels` ni en `ALLOWED_MODELS` |
| 422 | `invalid_request_error` | El JSON no cumple el esquema |
| 429 | `rate_limit_error` | Superaste las peticiones por minuto |
| 429 | `insufficient_quota` | Agotaste la cuota de tokens del día |
| 502 | `api_error` | Ollama no responde, o el modelo no soporta la operación |
| 500 | `api_error` | Error no controlado (mira los logs de uvicorn) |

La diferencia entre los dos 429 importa: `rate_limit_error` se resuelve esperando unos
segundos, `insufficient_quota` no se resuelve hasta el día siguiente o subiendo el límite.

---

# 5. Cómo se aplican los límites

Cada petición a `/v1` pasa por esta secuencia antes de llegar al modelo:

1. **Hash de la clave** — SHA-256 de lo que llega en `Authorization`, se busca en `ApiKeys`
2. **Validación** — `IsActive = 1` y `ExpiresAt` en el futuro (o nulo)
3. **Peticiones por minuto** — `RequestsPerMinute` de la clave, o el valor por defecto del `.env`
4. **Cuota de tokens** — se suma `TotalTokens` de hoy en `ApiKeyUsage` y se compara con
   `DailyTokenLimit`
5. **Modelo** — se resuelve contra `LlmModels`; si no está, 404

Recién ahí se llama a Ollama. Después: se cuentan los tokens, se acumula en `ApiKeyUsage`
y se inserta una fila en `RequestLogs`.

Nota sobre el rate limiting: por defecto es **en memoria**, así que los contadores viven en
el proceso. Con un solo worker de uvicorn funciona bien; si algún día levantas varios
workers o varias instancias, cambia a `RATE_LIMIT_BACKEND=redis` en el `.env` o cada worker
llevará su propia cuenta.

---

# 6. Probar todo de una vez

```python
from openai import OpenAI

client = OpenAI(api_key="sk_live_TU_CLAVE", base_url="http://localhost:8000/v1")

# 1. Modelos
print([m.id for m in client.models.list().data])

# 2. Chat
r = client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Di solo: funciona"}],
)
print(r.choices[0].message.content, r.usage)

# 3. Streaming
for chunk in client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Cuenta del 1 al 5"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
print()

# 4. Modelo no permitido -> debe fallar con 404
try:
    client.chat.completions.create(
        model="llama3:70b", messages=[{"role": "user", "content": "hola"}]
    )
except Exception as exc:
    print("Rechazado como se esperaba:", exc)
```

Y comprueba que quedó registrado:

```sql
SELECT TOP 10 Model, Endpoint, TotalTokens, DurationMs, StatusCode, CreatedAt
FROM dbo.RequestLogs ORDER BY CreatedAt DESC;

SELECT * FROM dbo.ApiKeyUsage;
```

Si los `RequestLogs` se llenan y `ApiKeyUsage` acumula, el gateway está haciendo su trabajo
completo: no solo reenvía a Ollama, sino que mide y cobra.
