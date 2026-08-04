"""RecordUsage: las dos fases y por qué están separadas."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.application.use_cases.admin.record_usage import RecordUsage
from app.domain.entities.request_log import RequestLog
from app.domain.value_objects.token_usage import TokenUsage
from app.infrastructure.db.scoped_record_usage import es_transitorio
from tests.fakes import FakeUnitOfWork


def _log(**kwargs) -> RequestLog:
    base = dict(api_key_id=1, model="qwen2.5:3b", endpoint="/v1/chat/completions")
    base.update(kwargs)
    return RequestLog(**base)


@pytest.mark.asyncio
async def test_registra_consumo_y_log() -> None:
    uow = FakeUnitOfWork()
    await RecordUsage(uow).execute(_log(total_tokens=15), TokenUsage(11, 4))

    hoy = datetime.now(timezone.utc).date()
    assert uow.usage.items[(1, hoy)].total_tokens == 15
    assert len(uow.logs.items) == 1


@pytest.mark.asyncio
async def test_las_fases_son_independientes() -> None:
    """Si falla el log, el consumo ya confirmado no se pierde.

    Es lo que impide que un valor que no cabe en RequestLogs haga desaparecer
    la facturación de una petición ya servida.
    """
    uow = FakeUnitOfWork()

    async def add_que_falla(log):
        raise RuntimeError("no cabe en la columna")

    uow.logs.add = add_que_falla
    log = _log(total_tokens=15)

    await RecordUsage(uow).increment_usage(log, TokenUsage(11, 4))
    with pytest.raises(RuntimeError):
        await RecordUsage(uow).add_log(log)

    hoy = datetime.now(timezone.utc).date()
    assert uow.usage.items[(1, hoy)].total_tokens == 15   # el cobro sobrevive


@pytest.mark.asyncio
async def test_no_se_cobra_sin_tokens() -> None:
    uow = FakeUnitOfWork()
    await RecordUsage(uow).execute(_log(status_code=502), TokenUsage(0, 0))
    assert uow.usage.items == {}      # nada que cobrar
    assert len(uow.logs.items) == 1   # pero el fallo sí queda auditado


@pytest.mark.asyncio
async def test_sin_api_key_no_se_acumula() -> None:
    uow = FakeUnitOfWork()
    await RecordUsage(uow).execute(_log(api_key_id=None, total_tokens=15), TokenUsage(11, 4))
    assert uow.usage.items == {}
    assert len(uow.logs.items) == 1


@pytest.mark.asyncio
async def test_reintentar_solo_la_fase_del_log_no_cobra_dos_veces() -> None:
    """El bug que evita el diseño en dos fases: reintentar el conjunto volvería
    a aplicar un incremento ya confirmado."""
    uow = FakeUnitOfWork()
    log = _log(total_tokens=15)
    usage = TokenUsage(11, 4)

    await RecordUsage(uow).increment_usage(log, usage)
    for _ in range(3):                       # tres intentos de la SEGUNDA fase
        await RecordUsage(uow).add_log(log)

    hoy = datetime.now(timezone.utc).date()
    assert uow.usage.items[(1, hoy)].total_tokens == 15   # cobrado una sola vez
    assert len(uow.logs.items) == 3


class ErrorFalso(Exception):
    def __init__(self, texto: str, invalidada: bool = False) -> None:
        super().__init__(texto)
        self.orig = texto
        self.connection_invalidated = invalidada


class TestEsTransitorio:
    """Qué errores de SQL Server merecen reintento."""

    def test_conexion_invalidada(self) -> None:
        assert es_transitorio(ErrorFalso("08S01 communication link failure", True)) is True

    def test_deadlock_1205(self) -> None:
        assert es_transitorio(ErrorFalso("[SQL Server] Transaction ... deadlock victim. 1205")) is True

    def test_lock_timeout_1222(self) -> None:
        assert es_transitorio(ErrorFalso("Lock request time out period exceeded. 1222")) is True

    def test_error_permanente_no_se_reintenta(self) -> None:
        assert es_transitorio(ErrorFalso("2628 String or binary data would be truncated")) is False

    def test_sintaxis_no_se_reintenta(self) -> None:
        assert es_transitorio(ErrorFalso("102 Incorrect syntax near '1'")) is False
