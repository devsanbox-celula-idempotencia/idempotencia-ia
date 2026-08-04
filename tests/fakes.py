"""Dobles de prueba: implementan los puertos del dominio sin base de datos ni red.

Que esto sea posible en 200 líneas es la ventaja concreta de la arquitectura:
los casos de uso dependen de interfaces, así que las pruebas de los endpoints no
necesitan SQL Server ni Ollama corriendo.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from typing import Any

from app.domain.entities.api_key import ApiKey
from app.domain.entities.model import LLMModel
from app.domain.entities.request_log import RequestLog
from app.domain.entities.usage import Usage
from app.domain.entities.user import User
from app.domain.exceptions import ProviderError
from app.domain.ports.services.llm_provider import LLMProvider
from app.domain.value_objects.token_usage import TokenUsage


def ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Repositorios en memoria
# --------------------------------------------------------------------------- #
class FakeUserRepository:
    def __init__(self, usuarios: list[User] | None = None) -> None:
        self.items = {u.id: u for u in (usuarios or [])}

    async def get_by_id(self, user_id: int) -> User | None:
        return self.items.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.items.values() if u.email == email), None)


class FakeApiKeyRepository:
    def __init__(self, claves: list[ApiKey] | None = None) -> None:
        self.items: dict[int, ApiKey] = {k.id: k for k in (claves or [])}
        self._siguiente_id = max(self.items, default=0) + 1
        self.touched: list[int] = []

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        return next((k for k in self.items.values() if k.key_hash == key_hash), None)

    async def get_by_id(self, api_key_id: int) -> ApiKey | None:
        return self.items.get(api_key_id)

    async def list_by_user(self, user_id: int) -> list[ApiKey]:
        return [k for k in self.items.values() if k.user_id == user_id]

    async def add(self, api_key: ApiKey) -> ApiKey:
        api_key.id = self._siguiente_id
        api_key.created_at = api_key.created_at or ahora()
        self.items[api_key.id] = api_key
        self._siguiente_id += 1
        return api_key

    async def touch(self, api_key_id: int) -> None:
        self.touched.append(api_key_id)
        if api_key_id in self.items:
            self.items[api_key_id].last_used_at = ahora()

    async def revoke(self, api_key_id: int) -> bool:
        clave = self.items.get(api_key_id)
        if clave is None:
            return False
        clave.is_active = False
        return True


class FakeUsageRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[int, date], Usage] = {}

    async def increment(self, api_key_id: int, day: date, usage: TokenUsage) -> None:
        fila = self.items.setdefault((api_key_id, day), Usage(api_key_id=api_key_id, day=day))
        fila.add(usage.prompt_tokens, usage.completion_tokens)

    async def get_daily(self, api_key_id: int, day: date) -> Usage | None:
        return self.items.get((api_key_id, day))

    async def get_range(self, api_key_id: int | None, start: date, end: date) -> list[Usage]:
        return sorted(
            (
                u
                for (k, d), u in self.items.items()
                if start <= d <= end and (api_key_id is None or k == api_key_id)
            ),
            key=lambda u: u.day,
        )

    async def tokens_since(self, api_key_id: int, start: date) -> int:
        return sum(u.total_tokens for (k, d), u in self.items.items() if k == api_key_id and d >= start)


class FakeRequestLogRepository:
    def __init__(self) -> None:
        self.items: list[RequestLog] = []

    async def add(self, log: RequestLog) -> None:
        log.id = len(self.items) + 1
        log.created_at = log.created_at or ahora()
        self.items.append(log)

    async def search(
        self,
        api_key_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RequestLog]:
        filas = [
            log
            for log in self.items
            if (api_key_id is None or log.api_key_id == api_key_id)
            and (since is None or (log.created_at and log.created_at >= since))
            and (until is None or (log.created_at and log.created_at <= until))
        ]
        filas.sort(key=lambda log: (log.created_at or ahora(), log.id or 0), reverse=True)
        return filas[offset : offset + limit]


class FakeModelRepository:
    def __init__(self, modelos: list[LLMModel] | None = None) -> None:
        self.items = list(modelos or [])

    async def list_all(self) -> list[LLMModel]:
        return [m for m in self.items if m.is_active]

    async def get_by_id(self, model_id: str) -> LLMModel | None:
        return next((m for m in self.items if m.id == model_id and m.is_active), None)


class FakeUnitOfWork:
    def __init__(
        self,
        users: FakeUserRepository | None = None,
        api_keys: FakeApiKeyRepository | None = None,
        models: FakeModelRepository | None = None,
    ) -> None:
        self.users = users or FakeUserRepository()
        self.api_keys = api_keys or FakeApiKeyRepository()
        self.usage = FakeUsageRepository()
        self.logs = FakeRequestLogRepository()
        self.models = models or FakeModelRepository()
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def close(self) -> None:
        self.closed += 1


# --------------------------------------------------------------------------- #
# Proveedor de LLM
# --------------------------------------------------------------------------- #
class FakeLLMProvider(LLMProvider):
    """Determinista y configurable. `fallo` simula que Ollama no responde."""

    def __init__(
        self,
        respuesta: str = "Hola desde el modelo",
        prompt_tokens: int = 11,
        completion_tokens: int = 4,
        finish_reason: str = "stop",
        fallo: Exception | None = None,
        chunks: list[dict[str, Any]] | None = None,
        sano: bool = True,
    ) -> None:
        self.respuesta = respuesta
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.finish_reason = finish_reason
        self.fallo = fallo
        self.chunks = chunks
        self.sano = sano
        self.llamadas: list[dict[str, Any]] = []

    async def list_models(self) -> list[LLMModel]:
        return [LLMModel(id="qwen2.5:3b", provider_model="qwen2.5:3b", owned_by="ollama")]

    async def chat(
        self, model: str, messages: list[dict[str, Any]], **options: Any
    ) -> tuple[str, TokenUsage, str]:
        self.llamadas.append({"model": model, "messages": messages, "options": options})
        if self.fallo:
            raise self.fallo
        return (
            self.respuesta,
            TokenUsage(self.prompt_tokens, self.completion_tokens),
            self.finish_reason,
        )

    async def chat_stream(
        self, model: str, messages: list[dict[str, Any]], **options: Any
    ) -> AsyncIterator[dict[str, Any]]:
        self.llamadas.append({"model": model, "messages": messages, "options": options})
        if self.fallo:
            raise self.fallo
        piezas = self.chunks if self.chunks is not None else [
            {"message": {"role": "assistant", "content": "Ho"}, "done": False},
            {"message": {"role": "assistant", "content": "la"}, "done": False},
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": self.finish_reason,
                "prompt_eval_count": self.prompt_tokens,
                "eval_count": self.completion_tokens,
            },
        ]
        for pieza in piezas:
            yield pieza

    async def embeddings(self, model: str, inputs: list[str]) -> tuple[list[list[float]], TokenUsage]:
        self.llamadas.append({"model": model, "inputs": inputs})
        if self.fallo:
            raise self.fallo
        return [[0.1, 0.2, 0.3] for _ in inputs], TokenUsage(len(inputs) * 2, 0)

    async def health(self) -> bool:
        return self.sano


class ProviderCaido(FakeLLMProvider):
    def __init__(self) -> None:
        super().__init__(fallo=ProviderError("Ollama no responde"), sano=False)


# --------------------------------------------------------------------------- #
# Registrador de consumo y contenedor
# --------------------------------------------------------------------------- #
class FakeUsageRecorder:
    """Equivalente a ScopedRecordUsage pero contra el UnitOfWork falso."""

    def __init__(self, uow: FakeUnitOfWork, fallo: Exception | None = None) -> None:
        self.uow = uow
        self.fallo = fallo
        self.registros: list[tuple[RequestLog, TokenUsage]] = []

    async def execute(self, log: RequestLog, usage: TokenUsage) -> None:
        self.registros.append((log, usage))
        if self.fallo:
            return   # igual que en producción: un fallo de auditoría no rompe la respuesta
        if log.api_key_id is not None and usage.total_tokens > 0:
            await self.uow.usage.increment(
                log.api_key_id, datetime.now(timezone.utc).date(), usage
            )
        await self.uow.logs.add(log)


class FakeContainer:
    def __init__(self, provider: LLMProvider, rate_limiter, hasher, key_generator) -> None:
        self.provider = provider
        self.rate_limiter = rate_limiter
        self.hasher = hasher
        self.key_generator = key_generator


class FakeSession:
    """Solo lo que usa /ready."""

    def __init__(self, fallo: Exception | None = None) -> None:
        self.fallo = fallo

    async def execute(self, *args: object, **kwargs: object) -> object:
        if self.fallo:
            raise self.fallo
        return object()
