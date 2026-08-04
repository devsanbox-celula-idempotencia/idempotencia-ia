"""Registro de consumo con sesión propia, aislado de la petición.

Se usa en TODOS los endpoints que llaman al modelo, por dos motivos:

1. La llamada al LLM puede tardar decenas de segundos. Si se mantuviera abierta
   la conexión de la petición durante ese rato, el servidor de base de datos la
   cerraría por inactividad y el INSERT posterior fallaría con `08S01`.
2. En streaming, FastAPI ya cerró las dependencias `yield` antes de que termine
   el cuerpo de la respuesta, y Starlette cancela el scope si el cliente corta.

Un fallo de auditoría nunca debe romper una respuesta que el modelo ya generó:
se registra el error y se sigue.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

import anyio
from sqlalchemy.exc import DBAPIError

from app.application.use_cases.admin.record_usage import RecordUsage
from app.domain.entities.request_log import RequestLog
from app.domain.value_objects.token_usage import TokenUsage
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

_MAX_INTENTOS = 3

# Errores de SQL Server transitorios POR DISEÑO: la aplicación debe reintentar.
# 1205 = deadlock victim, 1222 = lock request timeout, 40001 = serialization.
# El MERGE con HOLDLOCK sobre ApiKeyUsage es justo el patrón que los produce
# cuando varias peticiones de la misma clave escriben a la vez.
_TRANSITORIOS = ("1205", "1222", "40001")


def es_transitorio(exc: BaseException) -> bool:
    if getattr(exc, "connection_invalidated", False):
        return True
    return any(codigo in str(getattr(exc, "orig", exc)) for codigo in _TRANSITORIOS)


class ScopedRecordUsage:
    async def execute(self, log: RequestLog, usage: TokenUsage) -> None:
        # shield: si el cliente cortó la conexión, Starlette cancela el scope;
        # sin esto el registro se perdería y el consumo no se cobraría.
        with anyio.CancelScope(shield=True):
            # Cada fase se reintenta por separado. Reintentar el conjunto
            # volvería a aplicar un incremento de consumo ya confirmado, es
            # decir, cobraría el doble.
            await self._con_reintentos(lambda uc: uc.increment_usage(log, usage), "consumo")
            await self._con_reintentos(lambda uc: uc.add_log(log), "log")

    async def _con_reintentos(
        self, accion: Callable[[RecordUsage], Awaitable[None]], etiqueta: str
    ) -> None:
        for intento in range(1, _MAX_INTENTOS + 1):
            try:
                async with get_session_factory()() as session:
                    await accion(RecordUsage(SqlAlchemyUnitOfWork(session)))
                return
            except DBAPIError as exc:
                if es_transitorio(exc) and intento < _MAX_INTENTOS:
                    logger.warning(
                        "Error transitorio al registrar %s; reintento %s", etiqueta, intento
                    )
                    await anyio.sleep(0.1 * intento)
                    continue
                logger.exception("No se pudo registrar %s", etiqueta)
                return
            except Exception:  # noqa: BLE001
                logger.exception("No se pudo registrar %s", etiqueta)
                return
