from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.services import faq_ai


@pytest.fixture()
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        yield db

    await engine.dispose()


@pytest.fixture()
def faq_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    source_dir = tmp_path / "data"
    index_dir = tmp_path / "faq-index"
    cache_dir = tmp_path / "faq-models"
    source_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    faq_ai._faq_index_root.cache_clear()
    faq_ai._faq_embeddings_cache_root.cache_clear()
    faq_ai._get_local_embeddings.cache_clear()
    monkeypatch.setattr(faq_ai.settings, "faq_source_dir", str(source_dir))
    monkeypatch.setattr(faq_ai.settings, "faq_index_dir", str(index_dir))
    monkeypatch.setattr(faq_ai.settings, "faq_embeddings_cache_dir", str(cache_dir))

    yield {
        "source_dir": source_dir,
        "index_dir": index_dir,
        "cache_dir": cache_dir,
    }

    faq_ai._faq_index_root.cache_clear()
    faq_ai._faq_embeddings_cache_root.cache_clear()
    faq_ai._get_local_embeddings.cache_clear()


@pytest.fixture(autouse=True)
def _configure_faq_storage(faq_storage):
    yield
