"""Capa domain: reglas de negocio puras, sin HTTP ni base de datos."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta

import pytest

from app.domain.entities.api_key import ApiKey
from app.domain.entities.request_log import RequestLog
from app.domain.entities.usage import Usage
from app.domain.value_objects.token_usage import TokenUsage


def _clave(**kwargs) -> ApiKey:
    base = dict(id=1, user_id=1, name="test", key_hash="h", key_prefix="sk_live_x")
    base.update(kwargs)
    return ApiKey(**base)


class TestTokenUsage:
    def test_total(self) -> None:
        assert TokenUsage(10, 18).total_tokens == 28

    def test_cero(self) -> None:
        assert TokenUsage(0, 0).total_tokens == 0

    def test_es_inmutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            TokenUsage(1, 1).prompt_tokens = 5  # type: ignore[misc]


class TestApiKey:
    def test_activa_y_sin_caducidad_es_usable(self) -> None:
        assert _clave().is_usable(datetime.utcnow()) is True

    def test_inactiva_no_es_usable(self) -> None:
        assert _clave(is_active=False).is_usable(datetime.utcnow()) is False

    def test_expirada_no_es_usable(self) -> None:
        ahora = datetime.utcnow()
        assert _clave(expires_at=ahora - timedelta(seconds=1)).is_usable(ahora) is False

    def test_justo_al_expirar_no_es_usable(self) -> None:
        ahora = datetime.utcnow()
        assert _clave(expires_at=ahora).is_usable(ahora) is False

    def test_vigente_es_usable(self) -> None:
        ahora = datetime.utcnow()
        assert _clave(expires_at=ahora + timedelta(days=1)).is_usable(ahora) is True

    def test_touch_marca_el_uso(self) -> None:
        clave = _clave()
        ahora = datetime.utcnow()
        clave.touch(ahora)
        assert clave.last_used_at == ahora


class TestUsage:
    def test_acumula(self) -> None:
        usage = Usage(api_key_id=1, day=datetime.utcnow().date())
        usage.add(10, 18)
        usage.add(5, 5)
        assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens, usage.requests) == (
            15,
            23,
            38,
            2,
        )

    def test_cuenta_la_peticion_aunque_no_haya_tokens(self) -> None:
        usage = Usage(api_key_id=1, day=datetime.utcnow().date())
        usage.add(0, 0)
        assert usage.requests == 1


class TestRequestLogRecorta:
    """SQL Server no trunca: aborta el INSERT. Y como el fallo de auditoría se
    traga para no romper la respuesta, un valor largo haría perder el registro."""

    def test_client_ip(self) -> None:
        log = RequestLog(api_key_id=1, model="m", endpoint="/x", client_ip="a" * 4000)
        assert len(log.client_ip) == 45

    def test_error_en_unidades_utf16(self) -> None:
        log = RequestLog(api_key_id=1, model="m", endpoint="/x", error="😀" * 900)
        assert len(log.error.encode("utf-16-le")) // 2 == 1000

    def test_error_ascii_largo(self) -> None:
        log = RequestLog(api_key_id=1, model="m", endpoint="/x", error="e" * 5000)
        assert len(log.error) == 1000

    def test_valores_normales_no_se_tocan(self) -> None:
        log = RequestLog(
            api_key_id=1, model="qwen2.5:3b", endpoint="/v1/chat/completions",
            client_ip="203.0.113.9", error=None,
        )
        assert log.client_ip == "203.0.113.9"
        assert log.error is None
        assert log.model == "qwen2.5:3b"

    def test_modelo_y_endpoint_tambien_se_acotan(self) -> None:
        log = RequestLog(api_key_id=1, model="m" * 500, endpoint="/" * 500)
        assert len(log.model) == 100
        assert len(log.endpoint) == 100
