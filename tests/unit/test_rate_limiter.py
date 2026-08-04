"""Limitador en memoria."""
from __future__ import annotations

import pytest

from app.domain.value_objects.rate_limit import RateLimitPolicy
from app.infrastructure.cache.in_memory_rate_limiter import InMemoryRateLimiter


@pytest.mark.asyncio
async def test_sin_politica_todo_pasa() -> None:
    limitador = InMemoryRateLimiter()
    for _ in range(100):
        assert (await limitador.check("k", RateLimitPolicy())).allowed is True


@pytest.mark.asyncio
async def test_corta_al_superar_el_limite() -> None:
    limitador = InMemoryRateLimiter()
    politica = RateLimitPolicy(requests_per_minute=3)
    resultados = [(await limitador.check("k", politica)).allowed for _ in range(5)]
    assert resultados == [True, True, True, False, False]


@pytest.mark.asyncio
async def test_remaining_decrece() -> None:
    limitador = InMemoryRateLimiter()
    politica = RateLimitPolicy(requests_per_minute=3)
    assert (await limitador.check("k", politica)).remaining == 2
    assert (await limitador.check("k", politica)).remaining == 1


@pytest.mark.asyncio
async def test_las_claves_no_se_mezclan() -> None:
    limitador = InMemoryRateLimiter()
    politica = RateLimitPolicy(requests_per_minute=1)
    assert (await limitador.check("a", politica)).allowed is True
    assert (await limitador.check("b", politica)).allowed is True
    assert (await limitador.check("a", politica)).allowed is False
