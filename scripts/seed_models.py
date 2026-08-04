"""Carga el catálogo de modelos en la tabla LlmModels.

Uso:  python -m scripts.seed_models
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.infrastructure.config.settings import get_settings
from app.infrastructure.db.models.model_model import LLMModelModel
from app.infrastructure.db.session import dispose_engine, get_session_factory

MODELS = [
    {
        "ModelId": "qwen2.5:3b",
        "ProviderModel": "qwen2.5:3b",
        "OwnedBy": "local",
        "ContextLength": 32768,
        "SupportsEmbeddings": False,
    },
]


async def main() -> None:
    settings = get_settings()
    print(f"Base de datos: {settings.safe_database_url}")

    try:
        await _seed()
    finally:
        await dispose_engine()


async def _seed() -> None:
    async with get_session_factory()() as session:
        for item in MODELS:
            exists = (
                await session.execute(
                    select(LLMModelModel).where(LLMModelModel.ModelId == item["ModelId"])
                )
            ).scalar_one_or_none()
            if exists:
                print(f"  = {item['ModelId']} ya existe")
                continue
            session.add(LLMModelModel(**item))
            print(f"  + {item['ModelId']} insertado")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
