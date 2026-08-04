# =============================================================================
#  Ollama Gateway
#
#  Imagen en dos etapas: la de compilación trae los compiladores necesarios
#  para pyodbc, y la final solo se queda con el entorno virtual y las
#  bibliotecas de ejecución. Ahorra ~400 MB y quita gcc de la imagen que
#  llega a producción.
#
#  Python 3.12 a propósito: con versiones más nuevas puede que aún no existan
#  ruedas precompiladas de pydantic-core (Rust) ni de pyodbc (C).
# =============================================================================

# --------------------------------------------------------------- compilación
FROM python:3.12-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# --------------------------------------------------------------- ejecución
FROM python:3.12-slim-bookworm AS runtime

# Driver ODBC 18 para SQL Server (obligatorio: sin él la API arranca pero no
# conecta) y curl, que usa el HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /opt/venv /opt/venv

# Usuario sin privilegios: si alguien escapa del proceso, no es root.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /code
COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# --workers 1 a propósito: el limitador de peticiones por defecto guarda los
# contadores en memoria del proceso. Para escalar, pon RATE_LIMIT_BACKEND=redis
# y sube el número de workers.
#
# --forwarded-allow-ips=* confía en el X-Forwarded-For de quien llegue: solo es
# seguro porque el puerto se publica en 127.0.0.1 y únicamente Nginx lo alcanza.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
