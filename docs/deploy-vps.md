# Despliegue en VPS — guía paso a paso (4 GB de RAM)

Objetivo: que `https://api.tudominio.com/v1/chat/completions` funcione desde el SDK de OpenAI,
con Ollama y `qwen2.5:3b` corriendo en tu servidor.

Asume **Ubuntu 24.04 LTS**, acceso `root` por SSH y un dominio apuntando al VPS.

---

## 0. Antes de nada: la restricción de los 4 GB

Este es el punto que decide todo lo demás. Los números reales:

| Componente | RAM que necesita |
|---|---|
| Ubuntu + servicios base | ~0.4 GB |
| Ollama con `qwen2.5:3b` cargado | ~2.5–3 GB |
| SQL Server 2022 (mínimo de Microsoft) | 2 GB |
| Redis | ~0.05 GB |
| FastAPI (1 worker) | ~0.2 GB |
| **Total** | **~5.2 GB** |

**No caben los cinco en 4 GB.** SQL Server ni siquiera arranca si detecta menos de 2 GB
disponibles, y Ollama necesita casi 3 GB en el momento de la inferencia. Si los pones juntos,
el kernel va a matar procesos (OOM killer) en cuanto llegue la primera petición real.

Tienes tres salidas. Elige una antes de seguir:

### Opción A — Sacar SQL Server del VPS ✅ recomendada

Ollama + Redis + FastAPI en el VPS (~3.2 GB, entra cómodo) y la base de datos en otro lado:

- **Azure SQL Database** — tiene una capa gratuita permanente; es SQL Server administrado y tu
  `DATABASE_URL` casi no cambia (solo el host y `Encrypt=yes`).
- Un **segundo VPS pequeño** (2 GB) solo para la BD.
- Un **SQL Server que ya tengas** en otra máquina, expuesto por VPN o IP autorizada.

Es la única opción que aguanta uso real. El resto de la guía asume esta.

### Opción B — Todo en el VPS, apretado

Sirve para una demo o para desarrollo, no para producción con concurrencia:

- SQL Server limitado a 1.5 GB (`MSSQL_MEMORY_LIMIT_MB=1536`)
- Ollama descargando el modelo cuando está ocioso (`OLLAMA_KEEP_ALIVE=2m`)
- 4 GB de swap obligatorios

Va a haber latencia de varios segundos en la primera petición tras un rato de inactividad,
porque el modelo se recarga desde disco.

### Opción C — Subir el VPS a 8 GB

Si el proyecto es para clientes reales, esto cuesta unos pocos dólares más al mes y te ahorra
todos los problemas anteriores. En 8 GB corre todo junto sin trucos.

---

## 1. Preparar el servidor

Entra como root y crea un usuario para trabajar:

```bash
ssh root@TU_IP

adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

Desconéctate y vuelve a entrar como `deploy`. A partir de aquí todo se hace con ese usuario.

Actualiza y pon el firewall:

```bash
sudo apt update && sudo apt upgrade -y

sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Fíjate en lo que **no** abrimos: ni `11434` (Ollama) ni `1433` (SQL Server) ni `6379` (Redis).
Nadie desde fuera debe poder hablarle a Ollama directamente — ese es el sentido del gateway.

Crea swap (te salva de un OOM en un pico):

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# el modelo se lee mucho de disco: baja la agresividad del swap
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

Verifica:

```bash
free -h
```

---

## 2. Instalar Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
newgrp docker

docker --version
docker compose version
```

---

## 3. Instalar Ollama y descargar el modelo

Ollama va **nativo en el host**, no en Docker. En un VPS sin GPU, meterlo en un contenedor solo
añade una capa de overhead y complica el acceso a la memoria.

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

El instalador ya deja un servicio systemd. Configúralo para el poco RAM que tienes:

```bash
sudo systemctl edit ollama
```

Pega esto en el bloque editable:

```ini
[Service]
# Solo escucha en localhost: nadie desde internet llega a Ollama
Environment="OLLAMA_HOST=127.0.0.1:11434"
# Un solo modelo cargado, una sola petición a la vez
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
# Cuánto tiempo mantiene el modelo en RAM sin uso (Opción B: bájalo a 2m)
Environment="OLLAMA_KEEP_ALIVE=10m"
```

Recarga y descarga el modelo:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl enable ollama

ollama pull qwen2.5:3b
```

Comprueba que responde y cuánta memoria consume:

```bash
curl http://localhost:11434/api/tags

ollama run qwen2.5:3b "responde solo: ok"
free -h          # mira cuánto quedó libre con el modelo cargado
```

> Ese `free -h` es tu dato más importante. Si con el modelo cargado te quedan menos de 1.5 GB
> libres, olvídate de meter SQL Server en la misma máquina.

---

## 4. La base de datos

### Si elegiste la Opción A (BD fuera del VPS)

No instalas nada aquí. Solo necesitas la cadena de conexión, que irá en el `.env` del paso 6:

```
DATABASE_URL=mssql+aioodbc://usuario:password@tu-servidor.database.windows.net:1433/OllamaGateway?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes
```

Autoriza la IP del VPS en el firewall de tu servidor SQL (en Azure SQL: *Networking → Firewall rules*).

### Si elegiste la Opción B (todo junto)

SQL Server va en Docker con límite de memoria explícito. Lo verás en el `docker-compose.prod.yml`
del paso 7. El parámetro clave es:

```yaml
environment:
  MSSQL_MEMORY_LIMIT_MB: "1536"
  MSSQL_PID: "Express"
mem_limit: 1800m
```

`MSSQL_MEMORY_LIMIT_MB` le dice a SQL Server cuánta memoria puede usar para su buffer pool.
Sin ese límite, se come toda la RAM disponible y deja a Ollama sin nada.

---

## 5. Subir el código

Lo más cómodo es Git. Sube tu proyecto a GitHub (privado) y clónalo:

```bash
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/TU_USUARIO/ollama-gateway.git
cd ollama-gateway
```

Si prefieres no usar Git, desde tu PC con Windows:

```powershell
scp -r C:\Users\boter\Desktop\ollama-gateway deploy@TU_IP:~/apps/
```

Actualizar después es `git pull` (o repetir el `scp`).

---

## 6. Configurar el entorno de producción

```bash
cp .env.example .env
nano .env
```

Deja algo así:

```env
ENVIRONMENT=production
DEBUG=false

# Opción A: tu servidor externo. Opción B: sqlserver (nombre del servicio en compose)
DATABASE_URL=mssql+aioodbc://sa:PASSWORD_FUERTE@sqlserver:1433/OllamaGateway?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes

REDIS_URL=redis://redis:6379/0
RATE_LIMIT_ENABLED=true
DEFAULT_REQUESTS_PER_MINUTE=30
DEFAULT_REQUESTS_PER_DAY=2000
DEFAULT_TOKENS_PER_DAY=500000

# host.docker.internal apunta al host donde corre Ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
DEFAULT_MODEL=qwen2.5:3b
ALLOWED_MODELS=["qwen2.5:3b"]

API_KEY_PREFIX=sk_live_
ADMIN_TOKEN=GENERA_UNO_LARGO_Y_ALEATORIO

LOG_LEVEL=INFO
```

Genera el `ADMIN_TOKEN` así:

```bash
openssl rand -hex 32
```

Y protege el archivo:

```bash
chmod 600 .env
```

Un detalle de los límites: con 4 GB y `OLLAMA_NUM_PARALLEL=1`, tu servidor procesa **una petición
a la vez**. Un `DEFAULT_REQUESTS_PER_MINUTE` de 30 ya es generoso; ponerlo en 100 solo consigue
que las peticiones hagan cola y den timeout.

---

## 7. Levantar la aplicación

Crea `docker-compose.prod.yml` en la raíz del proyecto:

```yaml
services:
  api:
    build: .
    restart: unless-stopped
    env_file: .env
    ports:
      - "127.0.0.1:8000:8000"   # solo local; Nginx lo publica hacia fuera
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      - redis
    mem_limit: 400m
    command: >
      uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --maxmemory 64mb --maxmemory-policy allkeys-lru
    mem_limit: 100m

  # SOLO si elegiste la Opción B (todo en el VPS)
  # sqlserver:
  #   image: mcr.microsoft.com/mssql/server:2022-latest
  #   restart: unless-stopped
  #   environment:
  #     ACCEPT_EULA: "Y"
  #     MSSQL_SA_PASSWORD: "PASSWORD_FUERTE"
  #     MSSQL_PID: "Express"
  #     MSSQL_MEMORY_LIMIT_MB: "1536"
  #   mem_limit: 1800m
  #   volumes:
  #     - mssql_data:/var/opt/mssql

volumes:
  mssql_data:
```

Fíjate en `127.0.0.1:8000:8000`: la API **no** se expone directamente a internet. Solo Nginx la
alcanza. Si pones `8000:8000` a secas, Docker abre el puerto saltándose `ufw` y quedas expuesto.

Construye y arranca:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
```

La primera construcción tarda: la imagen instala el driver ODBC 18 de Microsoft.

---

## 8. Migraciones de base de datos

```bash
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

Si es la primera vez y aún no tienes migraciones generadas, primero (en tu PC, con la BD accesible):

```bash
alembic revision --autogenerate -m "esquema inicial"
git add alembic/versions && git commit -m "migración inicial" && git push
```

Y luego en el VPS: `git pull` + `alembic upgrade head`.

Después, carga el catálogo y crea tu primera API key:

```bash
docker compose -f docker-compose.prod.yml exec api python scripts/seed_models.py
docker compose -f docker-compose.prod.yml exec api python scripts/create_admin_key.py
```

Guarda la clave que imprime — solo se muestra una vez, porque en la BD queda únicamente el hash.

---

## 9. Nginx con HTTPS

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Crea `/etc/nginx/sites-available/ollama-gateway`:

```nginx
server {
    listen 80;
    server_name api.tudominio.com;

    # Un modelo de 3B en CPU puede tardar; sin esto Nginx corta a los 60s
    proxy_read_timeout 300s;
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Imprescindible para streaming (stream=true / SSE)
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
    }
}
```

Ese `proxy_buffering off` es el que hace que el streaming funcione. Con el buffering activado,
Nginx acumula la respuesta y el cliente recibe todo de golpe al final — el `stream=True` del SDK
deja de servir para nada.

Activa y genera el certificado:

```bash
sudo ln -s /etc/nginx/sites-available/ollama-gateway /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d api.tudominio.com
```

Certbot reescribe el bloque para HTTPS y deja la renovación automática programada.

---

## 10. Verificar desde tu PC

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk_live_LA_QUE_GENERASTE",
    base_url="https://api.tudominio.com/v1",
)

resp = client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Hola, ¿funcionas?"}],
)
print(resp.choices[0].message.content)
print(resp.usage)
```

Y el streaming:

```python
for chunk in client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Cuéntame un chiste corto"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

Si eso funciona, tu API es indistinguible de OpenAI para cualquier cliente.

Comprobaciones rápidas desde el servidor:

```bash
curl https://api.tudominio.com/health
curl -H "X-Admin-Token: TU_TOKEN" https://api.tudominio.com/admin/usage?start=2026-08-01&end=2026-08-31
```

---

## 11. Endurecer antes de dar acceso a nadie

- [ ] `ufw status` muestra solo 22, 80 y 443
- [ ] `curl http://TU_IP:11434` desde fuera **falla** (Ollama no es público)
- [ ] `curl http://TU_IP:8000` desde fuera **falla** (la API solo pasa por Nginx)
- [ ] `ADMIN_TOKEN` es aleatorio y largo, no el del `.env.example`
- [ ] La contraseña de `sa` no es la de ejemplo
- [ ] `DEBUG=false` y `DOCS_URL` cerrado o protegido si no quieres Swagger público
- [ ] `.env` con permisos `600` y fuera de Git
- [ ] Fail2ban para SSH: `sudo apt install -y fail2ban`

Sobre Swagger en producción: déjalo abierto solo si quieres que tus clientes lo usen como
documentación. Si no, en `.env`:

```env
DOCS_URL=
REDOC_URL=
OPENAPI_URL=
```

---

## 12. Operación diaria

```bash
# Ver logs
docker compose -f docker-compose.prod.yml logs -f api

# Reiniciar
docker compose -f docker-compose.prod.yml restart api

# Desplegar una versión nueva
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# Vigilar memoria (lo que más se te va a romper con 4 GB)
free -h
docker stats --no-stream
sudo journalctl -u ollama -f

# ¿Hubo OOM killer?
dmesg | grep -i "killed process"
```

Ese último comando es el que vas a consultar cuando la API se caiga sin explicación. Si aparecen
procesos matados, es la señal para pasar a la Opción A o C.

---

## Resumen de la decisión

| Escenario | Qué hacer |
|---|---|
| Demo o portafolio, tráfico casi nulo | Opción B, todo en el VPS, con swap y límites |
| Clientes reales, aunque sean pocos | Opción A: BD fuera del VPS |
| Varios modelos o concurrencia | Opción C: 8–16 GB, y considera GPU |

---

## Fuentes

- [Configure and customize SQL Server Linux containers — Microsoft Learn](https://learn.microsoft.com/en-us/sql/linux/sql-server-linux-docker-container-configure?view=sql-server-ver17)
- [Performance best practices: SQL Server memory on Linux — Microsoft Learn](https://learn.microsoft.com/en-us/sql/linux/configure/performance-best-practices-sql-server-memory?view=sql-server-ver17)
- [Running Qwen2.5 on Ollama: model sizes explained — Serverman](https://www.serverman.co.uk/ai/ollama/qwen2-5-on-ollama/)
- [Ollama RAM requirements by model size — ADHDecode](https://adhdecode.com/articles/ollama/ollama-memory-ram-requirements-model-sizes/)
