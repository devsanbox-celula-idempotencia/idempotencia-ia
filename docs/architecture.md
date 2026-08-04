# Decisiones de arquitectura

## 1. Por qué Clean Architecture aquí

El requisito de fondo no es "hablar con Ollama", es **poder cambiar de motor sin que los
clientes se enteren**. Eso se traduce en una sola abstracción clave: `LLMProvider`
(`app/domain/ports/services/llm_provider.py`). Los casos de uso dependen de esa interfaz,
nunca de `httpx` ni de las rutas `/api/chat` de Ollama.

Cambiar a vLLM o a OpenAI = escribir un nuevo adaptador en `infrastructure/llm/` y
registrarlo en el container. Ni el dominio ni la capa de presentación cambian.

## 2. Regla de dependencias

```
presentation ──┐
               ├──► application ──► domain
infrastructure ┘
```

- `domain` no importa nada externo (ni FastAPI, ni SQLAlchemy, ni Pydantic).
- `application` solo conoce `domain`.
- `infrastructure` y `presentation` conocen todo, pero nadie los conoce a ellos.

Si un import rompe esa dirección, la arquitectura ya se degradó.

## 3. Doble modelo de datos

Hay dos representaciones deliberadamente separadas:

| Capa | Representación | Para qué |
|---|---|---|
| `domain/entities` | dataclasses puras | Reglas de negocio |
| `infrastructure/db/models` | modelos SQLAlchemy | Tablas de SQL Server |
| `presentation/schemas` | modelos Pydantic | Contrato HTTP (formato OpenAI) |

Los `mappers` traducen entre ellas. Es más código, pero evita que un cambio de columna
en SQL Server se propague al contrato público de la API.

## 4. Compatibilidad con OpenAI

`presentation/schemas/openai/` replica los objetos de OpenAI
(`chat.completion`, `chat.completion.chunk`, `text_completion`, `list` de modelos, `embedding`).
`infrastructure/llm/openai_mapper.py` hace la traducción en ambos sentidos con Ollama.

Los errores también siguen el formato de OpenAI (`{"error": {...}}`), lo maneja
`presentation/middleware/error_handler.py` a partir de las excepciones de dominio.

## 5. Conteo de tokens

Dos estrategias detrás del mismo puerto `TokenCounter`:

1. `OllamaTokenCounter` — usa `prompt_eval_count` y `eval_count` que ya devuelve Ollama.
   Es el camino preferido: es lo que el modelo realmente procesó.
2. `TiktokenCounter` — cálculo local; fallback cuando el backend no reporta el conteo
   (por ejemplo, en streaming si se corta la conexión).

## 6. Rate limiting

`RateLimiter` como puerto, con dos implementaciones: `RedisRateLimiter` (producción) e
`InMemoryRateLimiter` (desarrollo y tests). La política vive en el value object
`RateLimitPolicy` y sale de la propia `ApiKey` o de los valores por defecto en `Settings`.

## 7. Seguridad de las API keys

Nunca se persiste la clave en claro. Al crearla se devuelve una única vez; en base de datos
queda `SHA256(key)` más un `key_prefix` visible para identificarla en el panel. La validación
hashea la clave entrante y busca por hash (índice único).

## 8. Streaming

`StreamChatCompletion` devuelve un `AsyncIterator`; la capa de presentación lo envuelve en
`StreamingResponse` con `media_type="text/event-stream"` y emite líneas
`data: {...}` con objetos `chat.completion.chunk`, cerrando con `data: [DONE]`.
El consumo se contabiliza al cerrar el stream.

## 9. Transacciones

`UnitOfWork` agrupa los repositorios en una sola sesión de SQLAlchemy, para que
"guardar el log + acumular el consumo" sea atómico.

## 10. Qué queda fuera a propósito

- Facturación y planes: modelados como concepto (`Plans` en el diseño de tablas) pero
  fuera del alcance de esta estructura inicial.
- Multi-tenant: hoy `User` → `ApiKey`; si aparecen organizaciones, se agrega una entidad
  por encima sin tocar los casos de uso de chat.
