# Runbook de despliegue — Ollama Gateway

Documento para quien opera el servidor. Autocontenido: no hace falta leer el resto
del repositorio.

Hay **dos rutas de despliegue** —Docker o systemd— que comparten casi todo. Los
pasos 1 a 5 y 7 a 11 son comunes; solo el paso 6 se bifurca.

---

## 0. Qué se despliega

Una API en FastAPI que expone un modelo LLM local (`qwen2.5:3b` sobre Ollama) con el
contrato de la API de OpenAI, añadiendo autenticación por API key, límites de uso y
auditoría en SQL Server.

```
Internet ──HTTPS──► Nginx :443                      (siempre en el host)
                      │  proxy_pass, sin buffering para SSE
                      ▼
                  API :8000                         (contenedor  o  systemd)
                      │  publicada SOLO en 127.0.0.1
        ┌─────────────┴─────────────┐
        ▼                           ▼
  Ollama :11434                SQL Server :1433
  nativo, systemd              externo
  solo escucha en localhost    solo auditoría y API keys
```

**Ollama va siempre nativo**, en las dos rutas. En un servidor sin GPU, meterlo en un
contenedor solo añade una capa sobre un proceso ya intensivo en memoria y complica el
acceso a la GPU si algún día la hay.

La base de datos es externa: el servidor no aloja ningún motor de base de datos.

### Requisitos

| Recurso | Mínimo | Recomendado | Por qué |
|---|---|---|---|
| RAM | 4 GB | 8 GB | Ollama con el modelo cargado ocupa ~2,5–3 GB |
| Disco | 15 GB | 30 GB | El modelo pesa ~2 GB; con Docker suma ~1,5 GB de imágenes |
| CPU | 2 vCPU | 4 vCPU | Sin GPU, la inferencia es CPU-bound |
| SO | Ubuntu 22.04 | Ubuntu 24.04 LTS | Los comandos asumen `apt` |

Puertos abiertos hacia fuera: **22, 80, 443**. Nada más.
Salida necesaria: **1433/tcp** hacia SQL Server.

### Reparto de memoria en un servidor de 4 GB

| Componente | RAM |
|---|---|
| Ubuntu + servicios base | ~0,4 GB |
| Ollama con `qwen2.5:3b` cargado | ~2,5–3 GB |
| API (1 worker) | ~0,2 GB |
| Nginx | ~0,03 GB |
| **Total** | **~3,2 GB** |

Entra, pero justo. Por eso **no se despliega SQL Server en esta máquina**: su mínimo
son 2 GB y no caben junto a Ollama. Si alguien lo intenta, el OOM killer empezará a
matar procesos en cuanto llegue la primera petición real.

### Antes de empezar, pide estos datos

- Host, puerto, base de datos, usuario y contraseña de SQL Server
- Dominio ya apuntando (registro A) a la IP del servidor
- Correo para los avisos de renovación del certificado
- URL del repositorio y credenciales de lectura

---

## 1. Elegir la ruta

| | **Docker** | **systemd** |
|---|---|---|
| Dependencias en el host | Docker | Python 3.12, driver ODBC 18, `build-essential` |
| Aislamiento | Contenedor sin privilegios, sistema de archivos de solo lectura | Proceso con `ProtectSystem=strict` |
| Reproducibilidad | La imagen fija Python y el driver ODBC | Depende de lo instalado en el servidor |
| Consumo extra | ~50 MB del demonio + ~1 GB de imágenes en disco | Ninguno |
| Rollback | `git checkout` + rebuild, o volver a una imagen etiquetada | `git checkout` + reinstalar dependencias |
| Riesgo típico | Publicar el puerto mal y saltarse `ufw` (ver 6A) | Que el driver ODBC no esté o sea otra versión |

**Recomendación:** Docker si vais a desplegar en más de un servidor o queréis
reproducibilidad; systemd si es una sola máquina y preferís no añadir el demonio.
Ambas rutas están probadas y usan el mismo `.env`.

---

## 2. Preparar el servidor *(común)*

```bash
# Como root
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy/
```

Desconecta y vuelve a entrar como `deploy`. Todo lo demás se hace con ese usuario.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ufw fail2ban curl gnupg unzip git

sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

Swap, para que un pico de memoria no active el OOM killer:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.d/99-swap.conf
sudo sysctl --system
free -h
```

---

## 3. Ollama y el modelo *(común)*

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Configuración para un servidor con poca RAM y sin GPU:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
# Solo localhost: nadie desde internet debe llegar a Ollama directamente.
Environment="OLLAMA_HOST=127.0.0.1:11434"
# Un modelo cargado, una inferencia a la vez.
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
# Cuánto se mantiene el modelo en RAM sin uso. Con 4 GB, bájalo a 2m.
Environment="OLLAMA_KEEP_ALIVE=10m"
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ollama
ollama pull qwen2.5:3b
```

Verificación:

```bash
curl -s http://127.0.0.1:11434/api/tags | grep -o 'qwen2.5:3b'
ollama run qwen2.5:3b "responde solo: ok"
free -h        # anota cuánta RAM queda con el modelo cargado
```

> Si con el modelo cargado quedan menos de 1 GB libres, el servidor está infradimensionado.
> Baja `OLLAMA_KEEP_ALIVE` a `2m` o amplía la RAM.

**Con Docker hay un detalle extra:** el contenedor alcanza este Ollama a través de
`host.docker.internal`, que los ficheros compose ya resuelven con `extra_hosts`. Si
Ollama estuviera escuchando en `0.0.0.0` en vez de `127.0.0.1`, quedaría expuesto a
internet — mantén el `OLLAMA_HOST` de arriba.

---

## 4. Código y configuración *(común)*

```bash
sudo mkdir -p /opt/ollama-gateway
sudo chown deploy:deploy /opt/ollama-gateway
git clone <URL_DEL_REPO> /opt/ollama-gateway
cd /opt/ollama-gateway

cp .env.example .env
chmod 600 .env
nano .env
```

Valores para producción:

```dotenv
ENVIRONMENT=production
DEBUG=false

# Documentación pública: vacía estas tres para ocultar Swagger
DOCS_URL=
REDOC_URL=
OPENAPI_URL=

# Base de datos por partes: no hay que codificar los símbolos de la contraseña
DB_HOST=<host-sql-server>
DB_PORT=1433
DB_NAME=<base>
DB_USER=<usuario>
DB_PASSWORD=<contraseña>
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUST_SERVER_CERTIFICATE=true
DB_ENCRYPT=false
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE_SECONDS=240

RATE_LIMIT_BACKEND=memory
RATE_LIMIT_ENABLED=true
DEFAULT_REQUESTS_PER_MINUTE=30
DEFAULT_REQUESTS_PER_DAY=2000
DEFAULT_TOKENS_PER_DAY=500000

# systemd: 127.0.0.1 · Docker: los compose lo sobreescriben con host.docker.internal
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TIMEOUT_SECONDS=300
DEFAULT_MODEL=qwen2.5:3b
ALLOWED_MODELS=["qwen2.5:3b"]

API_KEY_PREFIX=sk_live_
ADMIN_TOKEN=<generar>
CORS_ORIGINS=["https://tu-frontend.com"]

LOG_LEVEL=INFO
```

Genera el token de administración:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

> Con `ENVIRONMENT=production`, la aplicación **se niega a arrancar** si `ADMIN_TOKEN`
> sigue siendo el valor de ejemplo. Es intencionado.

Sobre `DEFAULT_REQUESTS_PER_MINUTE`: con `OLLAMA_NUM_PARALLEL=1` el servidor atiende
una inferencia a la vez. Poner 100 no da más capacidad, solo encola peticiones hasta
que dan timeout. 30 es realista para un modelo de 3B en CPU.

El `.env` **nunca** se sube al repositorio ni entra en la imagen de Docker (está en
`.gitignore` y en `.dockerignore`). Se inyecta en tiempo de ejecución.

---

## 5. Esquema de base de datos *(común)*

El script crea 4 tablas y no toca ninguna existente. Todas las sentencias van
protegidas con `IF OBJECT_ID(...) IS NULL`, así que es idempotente.

```bash
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
  | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
sudo apt install -y sqlcmd

sqlcmd -S <host>,1433 -U <usuario> -P '<contraseña>' -d <base> -C \
       -i /opt/ollama-gateway/scripts/sql/001_create_tables.sql
```

`scripts/sql/999_drop_tables.sql` lo deshace: borra solo esas 4 tablas, en el orden
correcto de claves foráneas.

La comprobación (`scripts/check_db.py`) se ejecuta después de desplegar, porque
necesita las dependencias de Python. Ver el paso 6 de cada ruta.

---

# 6A · Ruta Docker

## 6A.1 Instalar Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
newgrp docker

docker --version
docker compose version
```

## 6A.2 Construir y levantar

```bash
cd /opt/ollama-gateway
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f api
```

La primera construcción tarda varios minutos: la imagen instala el driver ODBC 18.

```bash
docker compose -f docker-compose.prod.yml ps      # STATUS debe decir (healthy)
curl -s http://127.0.0.1:8000/ready
docker compose -f docker-compose.prod.yml exec api python -m scripts.check_db
```

`check_db` debe listar en verde `Users`, `ApiKeys`, `ApiKeyUsage`, `RequestLogs` y
`LlmModels`.

## 6A.3 Dos cosas que hay que respetar

**El puerto se publica en `127.0.0.1:8000:8000`, nunca en `8000:8000`.**
Docker escribe reglas de iptables directamente y **se salta `ufw`**: con la forma
corta, el puerto queda abierto a internet aunque el cortafuegos diga lo contrario.
Compruébalo desde otra máquina:

```bash
curl --max-time 5 http://<IP-DEL-SERVIDOR>:8000/health    # debe fallar
```

**El `.env` no puede entrar en la imagen.** Si entrara, la contraseña de la base de
datos quedaría incrustada en una capa, visible con `docker history` para cualquiera
que descargue la imagen. Verifícalo:

```bash
docker run --rm ollama-gateway:latest ls -la /code/.env    # "No such file"
```

## 6A.4 Qué trae la imagen

| Decisión | Por qué |
|---|---|
| Construcción en dos etapas | La imagen final no lleva `gcc` ni cabeceras de compilación: ~400 MB menos |
| Python 3.12 fijado | Con versiones más nuevas puede que aún no haya ruedas de `pydantic-core` (Rust) ni `pyodbc` (C), y pip intentaría compilarlas |
| Usuario `appuser` (uid 10001) | El proceso no corre como root |
| `HEALTHCHECK` contra `/health` | Docker marca el contenedor como *unhealthy* si deja de responder |
| `read_only: true` + tmpfs en `/tmp` | Sistema de archivos inmutable. Si algo necesitara escribir, quita esa línea |
| `mem_limit: 512m`, `cpus: 1.0` | Un fallo de la API no puede dejar sin memoria a Ollama |
| `no-new-privileges` | El proceso no puede escalar privilegios |
| Rotación de logs (10 MB × 5) | Sin esto los logs de Docker crecen sin límite |
| `--workers 1` | El limitador guarda contadores en memoria del proceso (ver paso 11) |

## 6A.5 Perfiles opcionales (solo desarrollo)

El `docker-compose.yml` de desarrollo trae Ollama, Redis y SQL Server como perfiles,
para no arrancar 3 GB si no hacen falta:

```bash
docker compose up -d                                    # solo la API
docker compose --profile ollama --profile redis up -d   # + Ollama y Redis
docker compose exec ollama ollama pull qwen2.5:3b
```

**En el servidor de producción no uses el perfil `sqlserver`**: entre SQL Server
(2 GB mínimo) y Ollama (~3 GB) no caben en 4 GB. Ver el reparto de memoria del paso 0.

---

# 6B · Ruta systemd

## 6B.1 Driver ODBC 18

Sin esto, la API arranca pero no conecta a la base de datos.

```bash
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
  | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

# Ajusta la versión de Ubuntu si no es 24.04
echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/24.04/prod noble main" \
  | sudo tee /etc/apt/sources.list.d/mssql-release.list

sudo apt update
sudo ACCEPT_EULA=Y apt install -y msodbcsql18 unixodbc-dev

odbcinst -q -d      # debe listar [ODBC Driver 18 for SQL Server]
```

## 6B.2 Python y dependencias

```bash
sudo apt install -y python3.12 python3.12-venv python3-pip build-essential

cd /opt/ollama-gateway
python3.12 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install --only-binary=:all: -r requirements.txt

./.venv/bin/python -m scripts.check_db
```

> **Usa Python 3.12 o 3.13.** Con versiones más nuevas puede que aún no existan ruedas
> precompiladas de `pydantic-core` ni `pyodbc`, y pip intentaría compilarlas.
> `--only-binary=:all:` hace que falle rápido y con un mensaje claro en vez de intentarlo.

## 6B.3 Servicio systemd

```bash
sudo tee /etc/systemd/system/ollama-gateway.service >/dev/null <<'EOF'
[Unit]
Description=Ollama Gateway (API compatible con OpenAI)
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=exec
User=deploy
Group=deploy
WorkingDirectory=/opt/ollama-gateway
EnvironmentFile=/opt/ollama-gateway/.env
# --workers 1 a propósito: ver paso 11.
ExecStart=/opt/ollama-gateway/.venv/bin/uvicorn app.main:app \
          --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers \
          --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=30

# Endurecimiento
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/ollama-gateway

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ollama-gateway
sudo systemctl status ollama-gateway --no-pager

curl -s http://127.0.0.1:8000/ready
```

`--host 127.0.0.1` es deliberado: la API no se expone directamente, solo a través de
Nginx. `--forwarded-allow-ips=127.0.0.1` hace que se confíe en el `X-Forwarded-For`
de Nginx y no en el que envíe un cliente cualquiera.

---

## 7. Nginx y TLS *(común)*

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

sudo tee /etc/nginx/sites-available/ollama-gateway >/dev/null <<'EOF'
upstream gateway {
    server 127.0.0.1:8000;
    keepalive 16;
}

server {
    listen 80;
    server_name api.tudominio.com;

    # Un modelo de 3B en CPU puede tardar minutos. Con los 60 s por defecto,
    # Nginx cortaría la petición antes de que el modelo termine.
    proxy_read_timeout    300s;
    proxy_send_timeout    300s;
    proxy_connect_timeout  60s;

    client_max_body_size 10M;

    location / {
        proxy_pass http://gateway;
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection        "";

        # Imprescindible para el streaming SSE: con buffering, Nginx acumula
        # toda la respuesta y el cliente la recibe de golpe al final.
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/ollama-gateway /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d api.tudominio.com -m <correo> --agree-tos --redirect -n
sudo systemctl list-timers | grep certbot     # renovación automática
```

Nginx apunta a `127.0.0.1:8000` en ambas rutas: para él es indiferente que detrás haya
un contenedor o un proceso de systemd.

---

## 8. Primera API key *(común)*

Necesita un `UserId` que ya exista en la tabla `Users`. Si no existe, el script lista
los disponibles.

```bash
# Docker
docker compose -f docker-compose.prod.yml exec api \
  python -m scripts.create_admin_key --user-id 1 --name "cliente-piloto" --rpm 30

# systemd
cd /opt/ollama-gateway && ./.venv/bin/python \
  -m scripts.create_admin_key --user-id 1 --name "cliente-piloto" --rpm 30
```

La clave se imprime **una sola vez**; en base de datos solo queda su SHA-256.

Alternativa por API:

```bash
curl -s -X POST https://api.tudominio.com/admin/api-keys \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"user_id":1,"name":"cliente-piloto","requests_per_minute":30}'
```

---

## 9. Verificación de extremo a extremo *(común)*

```bash
KEY=sk_live_...

curl -s https://api.tudominio.com/health
curl -s https://api.tudominio.com/v1/models -H "Authorization: Bearer $KEY"

# Chat
curl -s -X POST https://api.tudominio.com/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:3b","messages":[{"role":"user","content":"Di solo: ok"}]}'

# Streaming (el -N desactiva el buffer de curl)
curl -sN -X POST https://api.tudominio.com/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:3b","messages":[{"role":"user","content":"Cuenta del 1 al 5"}],"stream":true}'

# Sin clave -> 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://api.tudominio.com/v1/chat/completions \
  -H "Content-Type: application/json" -d '{"model":"qwen2.5:3b","messages":[]}'

# Modelo no permitido -> 404
curl -s -X POST https://api.tudominio.com/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"llama3:70b","messages":[{"role":"user","content":"hola"}]}'
```

Y que la auditoría esté registrando:

```bash
curl -s "https://api.tudominio.com/admin/logs?limit=5" -H "X-Admin-Token: $ADMIN_TOKEN"
curl -s "https://api.tudominio.com/admin/usage?start=$(date -u +%F)&end=$(date -u +%F)" \
     -H "X-Admin-Token: $ADMIN_TOKEN"
```

Si `RequestLogs` se llena y `ApiKeyUsage` acumula, el despliegue está completo.

### Checklist de seguridad antes de dar acceso

- [ ] `sudo ufw status` muestra solo 22, 80 y 443
- [ ] `curl http://<IP>:11434` desde fuera **falla**
- [ ] `curl http://<IP>:8000` desde fuera **falla** (con Docker, comprobarlo de verdad: el demonio se salta `ufw`)
- [ ] Con Docker: `docker run --rm ollama-gateway:latest ls /code/.env` dice "No such file"
- [ ] `ADMIN_TOKEN` es aleatorio, no el de ejemplo
- [ ] `DEBUG=false` y `DOCS_URL` vacío si Swagger no debe ser público
- [ ] `.env` con permisos `600` y fuera del control de versiones
- [ ] HTTPS funcionando y el timer de `certbot` activo

---

## 10. Operación *(según la ruta)*

### Docker

```bash
cd /opt/ollama-gateway

make prod-logs                 # o: docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml restart api
docker stats --no-stream
docker compose -f docker-compose.prod.yml exec api bash

# Desplegar una versión nueva (git pull + build + verifica /ready, falla si no responde)
make prod-deploy

# Rollback
git checkout <commit-anterior>
docker compose -f docker-compose.prod.yml up -d --build

# Limpiar imágenes viejas cuando el disco apriete
docker image prune -f
```

### systemd

```bash
sudo systemctl status ollama-gateway
sudo journalctl -u ollama-gateway -f
sudo systemctl restart ollama-gateway

# Desplegar una versión nueva
cd /opt/ollama-gateway
git pull
./.venv/bin/pip install --only-binary=:all: -r requirements.txt
sudo systemctl restart ollama-gateway
curl -s http://127.0.0.1:8000/ready

# Rollback
git checkout <commit-anterior>
./.venv/bin/pip install --only-binary=:all: -r requirements.txt
sudo systemctl restart ollama-gateway
```

### Común

```bash
sudo journalctl -u ollama -f            # logs de Ollama
free -h
dmesg | grep -i "killed process"        # ¿actuó el OOM killer?
```

El esquema de base de datos es aditivo: una versión anterior del código funciona con
las tablas nuevas. Solo si hace falta revertir el esquema, usa
`scripts/sql/999_drop_tables.sql` (borra los datos de consumo y auditoría).

### Rotación de logs

Con Docker ya está configurada en el compose (10 MB × 5 archivos). Con systemd, acota
`journald`:

```bash
sudo sed -i 's/^#SystemMaxUse=.*/SystemMaxUse=500M/' /etc/systemd/journald.conf
sudo systemctl restart systemd-journald
```

En ambos casos, la tabla `RequestLogs` crece sin límite. Programa una limpieza mensual:

```sql
DELETE FROM dbo.RequestLogs WHERE CreatedAt < DATEADD(day, -90, SYSUTCDATETIME());
```

---

## 11. Diagnóstico de fallos

| Síntoma | Causa probable | Comprobación / arreglo |
|---|---|---|
| `/ready` con `database: false` | Cadena de conexión, driver ODBC o firewall del servidor SQL | `check_db` dice cuál de los tres falla (`exec api python -m scripts.check_db` en Docker) |
| `/ready` con `ollama: false` | Ollama caído, o el contenedor no lo alcanza | `systemctl status ollama`. Con Docker: `docker compose exec api curl -s http://host.docker.internal:11434/api/tags` |
| 502 con `api_error` | Ollama no responde o el modelo no está descargado | `ollama list`; `journalctl -u ollama` |
| 504 desde Nginx | `proxy_read_timeout` menor que el tiempo del modelo | Subirlo por encima de `OLLAMA_TIMEOUT_SECONDS` |
| El streaming llega de golpe al final | Falta `proxy_buffering off` | Revisar el bloque de Nginx |
| `08S01 communication link failure` | Conexión de base de datos cortada por inactividad | Ya mitigado con `DB_POOL_RECYCLE_SECONDS` y `pool_pre_ping`; si persiste, bájalo a 120 |
| 429 constantes | `DEFAULT_REQUESTS_PER_MINUTE` bajo, o varios workers con limitador en memoria | Subir el límite o pasar a `RATE_LIMIT_BACKEND=redis` |
| El servicio muere sin traza | OOM killer | `dmesg \| grep -i killed`; bajar `OLLAMA_KEEP_ALIVE` o ampliar RAM |
| Arranca y muere al instante | `ADMIN_TOKEN` con el valor de ejemplo en producción | Generar uno real; es una salvaguarda deliberada |
| El contenedor queda *unhealthy* | La API no responde en `/health` | `docker compose logs api`; suele ser el `.env` mal formado |
| El contenedor no arranca por permisos | `read_only: true` y algo intenta escribir | Quitar esa línea del `docker-compose.prod.yml` |
| El puerto 8000 responde desde internet | Se publicó como `8000:8000` | Cambiar a `127.0.0.1:8000:8000` y recrear el contenedor |

---

## 12. Escalar

Cuando un worker no dé abasto, en este orden:

1. **`RATE_LIMIT_BACKEND=redis`** y levantar Redis (perfil en el compose de desarrollo,
   o `apt install redis-server`). Hasta que esto esté, subir los workers **rompe los
   límites**: cada proceso llevaría su propia cuenta.
2. Subir el número de workers: `--workers N` en el `CMD` del contenedor o en el
   `ExecStart` de systemd.
3. Subir `OLLAMA_NUM_PARALLEL` solo si sobra RAM: cada inferencia concurrente necesita
   su propia caché de contexto.
4. Para varias instancias, un balanceador delante y Ollama en máquinas dedicadas,
   apuntando `OLLAMA_BASE_URL` a ellas. La API no guarda estado salvo los contadores
   del limitador, que para entonces ya estarán en Redis.

### Medir antes de decidir

El gateway registra la latencia y los tokens de cada petición, así que el
dimensionamiento sale de una consulta, no de una estimación:

```sql
SELECT
    COUNT(*)                                                       AS Peticiones,
    AVG(DurationMs)                                                AS LatenciaMediaMs,
    MAX(DurationMs)                                                AS LatenciaMaximaMs,
    AVG(CAST(CompletionTokens AS FLOAT) / NULLIF(DurationMs,0) * 1000) AS TokensPorSegundo
FROM dbo.RequestLogs
WHERE StatusCode = 200 AND CompletionTokens > 0
  AND CreatedAt >= DATEADD(day, -1, SYSUTCDATETIME());
```

`TokensPorSegundo` por debajo de 10 en un modelo de 3B indica que falta CPU. Y como el
servidor atiende una inferencia a la vez, la capacidad real es
`60 / (tokens_medios_por_respuesta / TokensPorSegundo)` peticiones por minuto.
