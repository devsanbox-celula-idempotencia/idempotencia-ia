"""Configuración central. Se lee del archivo .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "Ollama Gateway"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/v1"
    ADMIN_PREFIX: str = "/admin"

    # --- Swagger / OpenAPI (vaciar para ocultarlos en producción) ---
    DOCS_URL: str | None = "/docs"
    REDOC_URL: str | None = "/redoc"
    OPENAPI_URL: str | None = "/openapi.json"

    # --- SQL Server ---
    # Opción A: cadena completa. Cuidado con los símbolos de la contraseña:
    #   hay que codificarlos en porcentaje (] -> %5D, } -> %7D, @ -> %40, / -> %2F...).
    DATABASE_URL: str = Field(
        default=(
            "mssql+aioodbc://sa:Your_password123@localhost:1433/OllamaGateway"
            "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
        )
    )
    # Opción B (recomendada si la contraseña tiene símbolos raros): datos sueltos.
    # Si DB_HOST está definido, estos valores ganan y la cadena se arma sola,
    # escapando lo que haga falta.
    DB_HOST: str | None = None
    DB_PORT: int = 1433
    DB_NAME: str | None = None
    DB_USER: str | None = None
    DB_PASSWORD: str | None = None
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    DB_TRUST_SERVER_CERTIFICATE: bool = True
    DB_ENCRYPT: bool = False

    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 240

    @property
    def sqlalchemy_url(self) -> str:
        """La URL que realmente usa el motor.

        Con DB_HOST definido se construye con URL.create, que codifica la
        contraseña por su cuenta: así un `]` o un `}` dejan de romper el parseo.
        """
        if not self.DB_HOST:
            return self.DATABASE_URL

        from sqlalchemy.engine import URL

        query = {"driver": self.DB_DRIVER}
        if self.DB_TRUST_SERVER_CERTIFICATE:
            query["TrustServerCertificate"] = "yes"
        if self.DB_ENCRYPT:
            query["Encrypt"] = "yes"

        return URL.create(
            "mssql+aioodbc",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            query=query,
        ).render_as_string(hide_password=False)

    @property
    def safe_database_url(self) -> str:
        """La misma URL sin la contraseña, para poder mostrarla en logs."""
        import re

        return re.sub(r"//([^:/@]*):[^@]*@", r"//\1:***@", self.sqlalchemy_url)

    # --- Rate limiting ---
    RATE_LIMIT_BACKEND: str = "memory"          # "memory" o "redis"
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_ENABLED: bool = True
    DEFAULT_REQUESTS_PER_MINUTE: int = 60
    DEFAULT_REQUESTS_PER_DAY: int = 5000
    DEFAULT_TOKENS_PER_DAY: int = 1_000_000

    # --- Ollama ---
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_TIMEOUT_SECONDS: int = 300
    DEFAULT_MODEL: str = "qwen2.5:3b"
    ALLOWED_MODELS: list[str] = ["qwen2.5:3b"]

    # --- Seguridad ---
    API_KEY_PREFIX: str = "sk_live_"
    ADMIN_TOKEN: str = "change-me-admin-token"
    CORS_ORIGINS: list[str] = ["*"]

    # --- Observabilidad ---
    LOG_LEVEL: str = "INFO"
    METRICS_ENABLED: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
