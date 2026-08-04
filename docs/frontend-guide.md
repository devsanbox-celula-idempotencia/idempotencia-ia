# Guía de integración para el frontend

Cómo consumir el gateway desde una aplicación web. La API replica el contrato de
OpenAI, así que si ya has integrado ChatGPT en algo, esto te va a resultar familiar.

- **Base URL (producción):** `https://api.tudominio.com`
- **Base URL (local):** `http://localhost:8000`
- **Documentación interactiva:** `/docs` (Swagger) y `/redoc`
- **Esquema OpenAPI:** `/openapi.json` — sirve para generar el cliente TypeScript

---

## ⚠️ Antes de escribir código: dónde va la API key

**Una clave `sk_live_...` en el navegador es una clave pública.** Cualquiera abre las
DevTools, pestaña Network, y la copia. Con ella puede consumir tu cuota hasta agotarla
y tú lo pagas.

Esto no es un problema de este gateway: le pasa igual a OpenAI, y por eso su SDK de
JavaScript exige `dangerouslyAllowBrowser: true` para funcionar en el navegador.

Hay dos arquitecturas posibles:

### Opción A — Proxy en tu backend ✅ recomendada

```
Navegador ──sesión/cookie──► TU backend ──sk_live_...──► Gateway
```

El navegador nunca ve la clave. Tu backend la guarda como variable de entorno y añade
la cabecera. De paso puedes asociar cada petición al usuario que la hizo.

Ejemplo con Next.js (App Router), incluyendo streaming:

```ts
// app/api/chat/route.ts
export const runtime = "nodejs";

export async function POST(req: Request) {
  // Aquí validas la sesión del usuario antes de seguir
  const body = await req.json();

  const upstream = await fetch(`${process.env.GATEWAY_URL}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${process.env.GATEWAY_API_KEY}`,  // solo en el servidor
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  // Se reenvía el cuerpo tal cual: funciona igual con JSON y con SSE
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
      "Cache-Control": "no-cache",
    },
  });
}
```

Con Express:

```js
app.post("/api/chat", requireAuth, async (req, res) => {
  const upstream = await fetch(`${process.env.GATEWAY_URL}/v1/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.GATEWAY_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(req.body),
  });

  res.status(upstream.status);
  res.setHeader("Content-Type", upstream.headers.get("content-type") ?? "application/json");
  // Imprescindible para que el streaming llegue token a token
  res.flushHeaders();
  Readable.fromWeb(upstream.body).pipe(res);
});
```

Con este montaje **no necesitas CORS**: el navegador habla con tu propio dominio.

### Opción B — Llamada directa desde el navegador

Válida solo si se cumplen las tres:

1. Es una herramienta interna, detrás de VPN o de una red de confianza.
2. Cada usuario tiene **su propia** API key, con `requests_per_minute` y
   `daily_token_limit` acotados.
3. Asumes que esa clave se puede filtrar, y puedes revocarla en un minuto
   (`DELETE /admin/api-keys/{id}`).

Si vas por aquí, **nunca** metas la clave en el bundle: pídesela al usuario y guárdala
en memoria (no en `localStorage`, que sobrevive a la pestaña y es accesible desde
cualquier script inyectado).

El resto de la guía sirve para las dos opciones: cambia solo la URL a la que apuntas.

---

## CORS

Ya están autorizados estos orígenes:

| Origen | Para qué |
|---|---|
| `https://idempotencia.andrescortes.dev` | Frontend en producción |
| `http://100.99.206.50:8081` | Dashboard en la red interna |
| `http://localhost:3000` | Desarrollo (Next.js, CRA) |
| `http://localhost:5173` | Desarrollo (Vite) |

Se configuran en `CORS_ORIGINS` del `.env` del servidor. Para añadir uno más, se
edita esa lista y se reinicia el servicio.

**Es una lista de orígenes, no de URLs.** Un origen es `esquema://host:puerto`, sin
ruta ni barra final. `https://midominio.com/app` no es un origen válido;
`https://midominio.com` sí. Y `http://` y `https://` del mismo host son orígenes
distintos.

### Cabeceras que puedes leer desde JavaScript

Por defecto el navegador solo deja leer un puñado de cabeceras. Estas están
expuestas explícitamente:

| Cabecera | Contiene |
|---|---|
| `X-Request-ID` | Identificador de la petición. **Inclúyelo al reportar una incidencia**: aparece en los logs del servidor |
| `X-Response-Time-Ms` | Latencia total medida en el servidor |
| `X-RateLimit-Limit` | Peticiones por minuto de tu clave |
| `X-RateLimit-Remaining` | Cuántas te quedan en la ventana actual |
| `X-RateLimit-Reset` | Segundos hasta que se reinicie la ventana |
| `Retry-After` | Solo en los 429: segundos que debes esperar |

```ts
const res = await fetch(url, opciones);
console.log(res.headers.get("X-RateLimit-Remaining"));  // "27"
```

### Si te sale un error de CORS

| Mensaje en consola | Causa | Solución |
|---|---|---|
| `No 'Access-Control-Allow-Origin' header` | Tu origen no está en la lista | Pídele a backend que lo añada a `CORS_ORIGINS` |
| Falla al leer `X-Request-ID` | No está en `expose_headers` | Avisa a backend; la lista está en `app/main.py` |
| Falla solo en producción | Estás en `https` y el origen registrado es `http` (o al revés) | Registrar el origen exacto |
| Falla el preflight `OPTIONS` | Mandas una cabecera no permitida | Solo se aceptan `Authorization`, `Content-Type`, `X-Admin-Token` y `X-Request-ID` |

Un error de CORS **no** significa que la API haya fallado: la petición pudo ejecutarse
perfectamente y ser el navegador quien te oculte la respuesta. Compruébalo con curl.

---

## Autenticación

```
Authorization: Bearer sk_live_Yh2K9pQx7mZfR4tLvN8aB1cD6eG0sJwU
```

Todos los endpoints `/v1/*` la exigen. Sin ella, o con una clave inválida, revocada o
expirada: **401**.

Los endpoints `/admin/*` usan otra cabecera, `X-Admin-Token`, y **no deben llamarse
desde el navegador jamás**: ese token permite crear claves nuevas.

---

# Endpoints

## POST /v1/chat/completions

El principal. Con `stream: false` devuelve la respuesta completa; con `stream: true`,
un flujo SSE.

### Petición

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `model` | `string` | sí | `"qwen2.5:3b"` |
| `messages` | `Message[]` | sí | Mínimo uno |
| `stream` | `boolean` | no | `false` por defecto |
| `temperature` | `number` 0–2 | no | 0 = determinista, 0.7 = equilibrado |
| `top_p` | `number` 0–1 | no | |
| `max_tokens` | `number` 1–131072 | no | **El que más afecta al tiempo de respuesta** |
| `stop` | `string \| string[]` | no | Hasta 4 secuencias |
| `presence_penalty` | `number` −2–2 | no | |
| `frequency_penalty` | `number` −2–2 | no | |
| `n` | `number` | no | Solo se admite `1`; con más, 400 |
| `user` | `string` | no | Se acepta y se ignora |

`Message` es `{ role: "system" | "user" | "assistant" | "tool", content: string }`.
Los roles van **en inglés**: es el contrato de OpenAI.

### Respuesta

```json
{
  "id": "chatcmpl-4f3a9c2b8d1e6f0a7b2c3d4e",
  "object": "chat.completion",
  "created": 1785790000,
  "model": "qwen2.5:3b",
  "choices": [{
    "index": 0,
    "message": { "role": "assistant", "content": "Una API REST es..." },
    "finish_reason": "stop"
  }],
  "usage": { "prompt_tokens": 28, "completion_tokens": 142, "total_tokens": 170 }
}
```

`finish_reason` puede ser `"stop"` (terminó solo) o `"length"` (se cortó por
`max_tokens`). **Si es `"length"`, la respuesta está truncada**: avísale al usuario o
pide continuación.

### Ejemplo sin streaming

```ts
async function preguntar(pregunta: string) {
  const res = await fetch("/api/chat", {          // tu proxy
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "qwen2.5:3b",
      messages: [
        { role: "system", content: "Responde en español, máximo 3 frases." },
        { role: "user", content: pregunta },
      ],
      temperature: 0.7,
      max_tokens: 300,
    }),
  });

  if (!res.ok) throw await parsearError(res);

  const data = await res.json();
  return {
    texto: data.choices[0].message.content,
    truncado: data.choices[0].finish_reason === "length",
    tokens: data.usage.total_tokens,
  };
}
```

### Streaming

**No uses `EventSource`**: solo hace peticiones GET y no permite cabeceras. Hay que
leer el cuerpo con `fetch` + `ReadableStream`.

```ts
async function* chatStream(
  mensajes: Message[],
  signal?: AbortSignal,
): AsyncGenerator<string> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: "qwen2.5:3b", messages: mensajes, stream: true }),
    signal,
  });

  if (!res.ok) throw await parsearError(res);
  if (!res.body) throw new Error("Sin cuerpo en la respuesta");

  const lector = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await lector.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Los eventos SSE se separan por línea en blanco. Es imprescindible
    // acumular en un buffer: un chunk de red puede cortar un evento por la mitad.
    const partes = buffer.split("\n\n");
    buffer = partes.pop() ?? "";

    for (const parte of partes) {
      const linea = parte.trim();
      if (!linea.startsWith("data:")) continue;

      const carga = linea.slice(5).trim();
      if (carga === "[DONE]") return;          // último evento, no es JSON

      const chunk = JSON.parse(carga);
      const delta = chunk.choices[0]?.delta?.content;
      if (delta) yield delta;
    }
  }
}
```

Uso:

```ts
const controlador = new AbortController();

let texto = "";
for await (const trozo of chatStream(mensajes, controlador.signal)) {
  texto += trozo;
  setRespuesta(texto);       // se pinta según llega
}

// Para cancelar (botón "Detener"):
controlador.abort();
```

Formato de los eventos, por si necesitas depurarlo:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant","content":"Ho"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"la"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

Tres detalles que sorprenden:

- **Los chunks no traen `usage`.** Es así también en OpenAI. Si necesitas mostrar los
  tokens consumidos, consúltalos luego en `/admin/usage` desde tu backend.
- **El último evento es literalmente `data: [DONE]`**, no un JSON. Si intentas
  parsearlo, revienta.
- **Cancelar no te devuelve el dinero.** Los tokens ya generados se contabilizan igual:
  el servidor los registra aunque cortes la conexión.

---

## POST /v1/completions

API antigua: un `prompt` plano en vez de mensajes. Existe por compatibilidad.

```ts
await fetch("/api/completions", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ model: "qwen2.5:3b", prompt: "El cielo es", max_tokens: 50 }),
});
```

Respuesta: igual que el chat pero con `choices[0].text` en vez de `.message.content`.

**No admite streaming** (devuelve 400) ni `n > 1`. Para chat en tiempo real, usa
`/v1/chat/completions`.

---

## GET /v1/models

Para poblar un desplegable de modelos.

```ts
const { data } = await (await fetch("/api/models")).json();
// data: [{ id: "qwen2.5:3b", object: "model", created: 1767225600, owned_by: "local" }]
```

`GET /v1/models/{id}` devuelve uno solo, o **404** `model_not_found` si no está
habilitado.

---

## POST /v1/embeddings

Vectores para búsqueda semántica o similitud.

```ts
const res = await fetch("/api/embeddings", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ model: "nomic-embed-text", input: ["hola", "mundo"] }),
});
// data: [{ object: "embedding", index: 0, embedding: [0.021, -0.114, ...] }, ...]
```

`input` acepta un texto o hasta 512. **No uses `qwen2.5:3b` aquí**: es un modelo de
chat y devolverá 502. Hace falta un modelo de embeddings habilitado en el servidor.

Validaciones: lista vacía, texto vacío o más de 512 elementos → **422**.

---

## GET /health y GET /ready

Sin autenticación. `/health` dice si el proceso vive; `/ready` comprueba además la base
de datos y Ollama:

```json
{ "status": "ok", "database": true, "ollama": true }
```

Útil para una pantalla de estado. Si `status` es `"degraded"`, el chat va a fallar.

---

## Endpoints /admin

`POST/GET/DELETE /admin/api-keys`, `GET /admin/usage`, `GET /admin/logs`.

**Desde el navegador, nunca.** Requieren `X-Admin-Token`, que permite crear claves
nuevas: exponerlo equivale a regalar la API. Si necesitas un panel de administración,
que tu backend haga de intermediario y valide que el usuario es administrador.

Los detalles de estos endpoints están en `docs/api-endpoints.md`.

---

# Errores

Todos comparten el mismo formato, el de OpenAI:

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

| HTTP | `type` | Qué pasó | Qué hacer en el front |
|---|---|---|---|
| 400 | `invalid_request_error` | `n > 1`, o `stream` en `/v1/completions` | Corregir la petición. Es un bug tuyo |
| 401 | `invalid_request_error` | Clave ausente, inválida, revocada o expirada | Cerrar sesión o avisar de que hay que renovar la clave |
| 403 | `invalid_request_error` | `X-Admin-Token` incorrecto | No deberías estar llamando a `/admin` |
| 404 | `model_not_found` | El modelo no está habilitado | Mostrar los de `GET /v1/models` |
| 422 | `invalid_request_error` | El cuerpo no cumple el esquema | Revisa `message`: dice el campo exacto |
| 429 | `rate_limit_error` | Demasiadas peticiones por minuto | Esperar `Retry-After` segundos y reintentar |
| 429 | `insufficient_quota` | Cuota diaria de tokens agotada | **No reintentar**: no se arregla hasta mañana |
| 500 | `api_error` | Fallo no controlado | Mostrar error genérico y reportar el `X-Request-ID` |
| 502 | `api_error` | El modelo no responde | Reintentar una vez; si sigue, avisar de que el servicio está caído |

**Los dos 429 son distintos y hay que tratarlos distinto.** `rate_limit_error` se pasa
esperando segundos; `insufficient_quota` no se pasa reintentando, y hacerlo solo genera
ruido.

### Parseo y reintentos

```ts
export class GatewayError extends Error {
  constructor(
    public status: number,
    public type: string,
    message: string,
    public retryAfter?: number,
    public requestId?: string,
  ) {
    super(message);
  }

  /** ¿Tiene sentido reintentar esto? */
  get esReintentable() {
    return this.status === 502 || this.type === "rate_limit_error";
  }
}

export async function parsearError(res: Response): Promise<GatewayError> {
  let mensaje = `Error ${res.status}`;
  let tipo = "unknown";

  try {
    const cuerpo = await res.json();
    mensaje = cuerpo?.error?.message ?? mensaje;
    tipo = cuerpo?.error?.type ?? tipo;
  } catch {
    /* la respuesta no era JSON: nos quedamos con el genérico */
  }

  const retryAfter = res.headers.get("Retry-After");
  return new GatewayError(
    res.status,
    tipo,
    mensaje,
    retryAfter ? Number(retryAfter) : undefined,
    res.headers.get("X-Request-ID") ?? undefined,
  );
}
```

Reintento con espera respetando `Retry-After`:

```ts
export async function conReintentos<T>(fn: () => Promise<T>, intentos = 3): Promise<T> {
  for (let i = 1; i <= intentos; i++) {
    try {
      return await fn();
    } catch (e) {
      const esUltimo = i === intentos;
      if (!(e instanceof GatewayError) || !e.esReintentable || esUltimo) throw e;

      // El servidor dice cuánto esperar; si no, retroceso exponencial
      const esperaMs = (e.retryAfter ?? 2 ** i) * 1000;
      await new Promise((r) => setTimeout(r, esperaMs));
    }
  }
  throw new Error("inalcanzable");
}
```

### Mensajes para el usuario

No enseñes el `message` crudo: menciona límites internos y nombres de modelo.

```ts
const MENSAJES: Record<string, string> = {
  rate_limit_error:  "Vas muy rápido. Espera unos segundos y vuelve a intentarlo.",
  insufficient_quota:"Has agotado el uso de hoy. Se renueva mañana.",
  model_not_found:   "Ese modelo no está disponible.",
  api_error:         "El servicio no está disponible ahora mismo. Inténtalo en un momento.",
};

function mensajeUsuario(e: unknown) {
  if (e instanceof GatewayError) {
    if (e.status === 401) return "Tu sesión ha caducado. Vuelve a iniciar sesión.";
    return MENSAJES[e.type] ?? "Ha ocurrido un error. Inténtalo de nuevo.";
  }
  return "No se pudo conectar. Revisa tu conexión.";
}
```

---

# Rendimiento: lo que hay que saber antes de diseñar la UI

El modelo corre en CPU en el servidor. Órdenes de magnitud reales:

| Situación | Tiempo |
|---|---|
| Generar 100 tokens | ~5 s |
| Generar 300 tokens | ~15 s |
| Primera petición tras 10 min de inactividad | +3-5 s (se recarga el modelo) |

**Una respuesta de 12 segundos es normal, no un fallo.** Consecuencias de diseño:

1. **Usa streaming siempre que muestres texto a una persona.** El total es el mismo,
   pero el primer token llega en menos de un segundo. Es la diferencia entre "funciona"
   y "está colgado".
2. **Limita `max_tokens`.** Es lo único que reduce el tiempo real. 150 para respuestas
   cortas, 500 como techo.
3. **Pide brevedad en el `system`.** `"Responde en máximo 3 frases"` suele bajar más el
   tiempo que el propio `max_tokens`, porque el modelo deja de escribir relleno.
4. **Pon un timeout generoso.** Menos de 60 s cortará respuestas legítimas. El servidor
   admite hasta 300 s.
5. **Deshabilita el botón de enviar mientras hay una petición en vuelo.** El servidor
   atiende **una inferencia a la vez**: dos peticiones simultáneas no van el doble de
   rápido, se encolan.
6. **Ofrece un botón de cancelar** con `AbortController`. Con streaming es lo que
   convierte una espera larga en algo tolerable.

---

# Tipos TypeScript

```ts
export type Role = "system" | "user" | "assistant" | "tool";

export interface Message {
  role: Role;
  content: string;
}

export interface ChatRequest {
  model: string;
  messages: Message[];
  stream?: boolean;
  temperature?: number;      // 0–2
  top_p?: number;            // 0–1
  max_tokens?: number;       // 1–131072
  stop?: string | string[];  // hasta 4
  presence_penalty?: number; // −2–2
  frequency_penalty?: number;// −2–2
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ChatResponse {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: Array<{
    index: number;
    message: Message;
    finish_reason: "stop" | "length" | null;
  }>;
  usage: Usage;
}

export interface ChatChunk {
  id: string;
  object: "chat.completion.chunk";
  created: number;
  model: string;
  choices: Array<{
    index: number;
    delta: { role?: Role; content?: string };
    finish_reason: "stop" | "length" | null;
  }>;
}

export interface ApiError {
  error: { message: string; type: string; param: string | null; code: string | null };
}
```

Si prefieres no escribirlos a mano, genéralos del esquema:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/gateway.d.ts
```

---

# Hook de React completo

```tsx
import { useCallback, useRef, useState } from "react";

export function useChat() {
  const [mensajes, setMensajes] = useState<Message[]>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const enviar = useCallback(async (texto: string) => {
    setError(null);
    setCargando(true);

    const historial: Message[] = [...mensajes, { role: "user", content: texto }];
    setMensajes([...historial, { role: "assistant", content: "" }]);

    const controlador = new AbortController();
    abortRef.current = controlador;

    try {
      let acumulado = "";
      for await (const trozo of chatStream(historial, controlador.signal)) {
        acumulado += trozo;
        setMensajes((prev) => {
          const copia = [...prev];
          copia[copia.length - 1] = { role: "assistant", content: acumulado };
          return copia;
        });
      }
    } catch (e) {
      // Cancelar no es un error que haya que mostrar
      if ((e as Error)?.name !== "AbortError") setError(mensajeUsuario(e));
    } finally {
      setCargando(false);
      abortRef.current = null;
    }
  }, [mensajes]);

  const cancelar = useCallback(() => abortRef.current?.abort(), []);

  return { mensajes, enviar, cancelar, cargando, error };
}
```

---

# Usar el SDK oficial de OpenAI

Como la API es compatible, el paquete `openai` funciona cambiando solo `baseURL`. En tu
**backend**:

```bash
npm install openai
```

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.GATEWAY_API_KEY,
  baseURL: `${process.env.GATEWAY_URL}/v1`,
});

const stream = await client.chat.completions.create({
  model: "qwen2.5:3b",
  messages: [{ role: "user", content: "Hola" }],
  stream: true,
});

for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}
```

Te ahorra el parseo de SSE y los reintentos. En el navegador exigiría
`dangerouslyAllowBrowser: true`, y ese nombre es una advertencia, no un trámite: lee la
sección del principio.

---

# Checklist antes de salir a producción

- [ ] La API key **no** aparece en el bundle del navegador (búscala en los archivos compilados)
- [ ] El origen de producción está en `CORS_ORIGINS`, con el esquema correcto
- [ ] Los 429 se distinguen: `rate_limit_error` reintenta, `insufficient_quota` no
- [ ] El botón de enviar se deshabilita mientras hay una petición en vuelo
- [ ] Hay botón de cancelar con `AbortController`
- [ ] El timeout del cliente es de al menos 60 s
- [ ] `finish_reason: "length"` se detecta y se avisa de que la respuesta está cortada
- [ ] Los mensajes de error que ve el usuario están traducidos, no son el `message` crudo
- [ ] El `X-Request-ID` se registra en tu telemetría para poder cruzarlo con el servidor
- [ ] Nada del frontend llama a `/admin/*`

---

# Depurar

```bash
# ¿Responde la API?
curl https://api.tudominio.com/health

# ¿Está bien mi clave?
curl https://api.tudominio.com/v1/models -H "Authorization: Bearer sk_live_..."

# ¿Está autorizado mi origen? (simula el preflight del navegador)
curl -i -X OPTIONS https://api.tudominio.com/v1/chat/completions \
  -H "Origin: https://idempotencia.andrescortes.dev" \
  -H "Access-Control-Request-Method: POST"
# Debe aparecer: access-control-allow-origin: https://idempotencia.andrescortes.dev

# Ver el streaming crudo (-N desactiva el buffer de curl)
curl -N -X POST https://api.tudominio.com/v1/chat/completions \
  -H "Authorization: Bearer sk_live_..." -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:3b","messages":[{"role":"user","content":"hola"}],"stream":true}'
```

Si algo falla, pásale a backend el **`X-Request-ID`** de la respuesta: con él encuentran
la petición exacta en los logs del servidor y en la tabla de auditoría.
