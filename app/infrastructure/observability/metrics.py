"""Métricas Prometheus (opcional): latencia, tokens, errores por modelo."""
from __future__ import annotations

from fastapi import FastAPI


def setup_metrics(app: FastAPI) -> None:
    """TODO: exponer /metrics con prometheus-fastapi-instrumentator."""
    raise NotImplementedError
