from __future__ import annotations

from pathlib import Path

import pytest

from app.db.enums import RoleCode
from app.db.models import Role, TelegramAccount, User
from app.services import faq_ai


class DummyFastEmbedEmbeddings:
    def __init__(self, *args, **kwargs):
        pass

    def _embed(self, text: str) -> list[float]:
        normalized = text.casefold()
        return [
            5.0 if "telegram" in normalized else 0.0,
            3.0 if "рейтинг" in normalized else 0.0,
            float(len(normalized) % 11),
        ]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_load_faq_items_maps_markdown_files_to_stable_entries(faq_storage):
    source_dir = faq_storage["source_dir"]
    _write_markdown(source_dir / "general" / "telegram-binding.md", "Откройте mini app и отправьте заявку.")
    _write_markdown(source_dir / "teacher" / "broadcast.md", "Рассылки доступны преподавателю.")

    items = faq_ai.load_faq_items()

    assert [item.category_name for item in items] == ["general", "teacher"]
    assert items[0].question == "telegram-binding"
    assert items[0].source_path == "general/telegram-binding.md"
    assert items[0].item_id == faq_ai.load_faq_items()[0].item_id


@pytest.mark.asyncio
async def test_async_faq_facades_match_markdown_backed_results(faq_storage):
    source_dir = faq_storage["source_dir"]
    _write_markdown(source_dir / "general" / "telegram-binding.md", "Откройте mini app и отправьте заявку.")

    items = await faq_ai.load_faq_items_async()
    categories = await faq_ai.list_faq_categories_async()
    rows = await faq_ai.list_faq_item_rows_async("telegram")
    status = await faq_ai.get_faq_index_status_async()

    assert items[0].question == "telegram-binding"
    assert categories[0]["name"] == "general"
    assert rows[0]["question"] == "telegram-binding"
    assert status["status"] == "missing"


@pytest.mark.asyncio
async def test_rebuild_faq_index_writes_manifest_and_reports_stale_after_source_change(faq_storage, monkeypatch):
    source_dir = faq_storage["source_dir"]
    _write_markdown(source_dir / "general" / "telegram-binding.md", "Откройте mini app и отправьте заявку.")

    faq_ai._get_local_embeddings.cache_clear()
    monkeypatch.setattr("langchain_community.embeddings.fastembed.FastEmbedEmbeddings", DummyFastEmbedEmbeddings)
    monkeypatch.setattr(faq_ai, "_embedding_cache_has_files", lambda _path: True)

    rebuilt = await faq_ai.rebuild_faq_index()
    status = faq_ai.get_faq_index_status()

    assert rebuilt["status"] == "ready"
    assert rebuilt["chunk_count"] >= 1
    assert (faq_storage["index_dir"] / "manifest.json").exists()
    assert (faq_storage["index_dir"] / "vectorstore").exists()
    assert status["status"] == "ready"

    _write_markdown(source_dir / "general" / "telegram-binding.md", "Измененный ответ для FAQ.")

    assert faq_ai.get_faq_index_status()["status"] == "stale"


def test_get_local_embeddings_fails_fast_without_local_model_cache(faq_storage):
    faq_ai._get_local_embeddings.cache_clear()

    with pytest.raises(RuntimeError, match="FAQ embedding model cache is empty"):
        faq_ai._get_local_embeddings()


@pytest.mark.asyncio
async def test_generate_assistant_reply_uses_markdown_backed_vector_context(session, faq_storage, monkeypatch):
    source_dir = faq_storage["source_dir"]
    _write_markdown(source_dir / "general" / "telegram-binding.md", "Откройте mini app и отправьте заявку на привязку.")

    faq_ai._get_local_embeddings.cache_clear()
    monkeypatch.setattr("langchain_community.embeddings.fastembed.FastEmbedEmbeddings", DummyFastEmbedEmbeddings)
    monkeypatch.setattr(faq_ai, "_embedding_cache_has_files", lambda _path: True)

    await faq_ai.rebuild_faq_index()

    student_role = Role(code=RoleCode.STUDENT, name="Student")
    user = User(username="faq_student", full_name="FAQ Student", password_hash="x", must_change_password=False)
    user.roles.append(student_role)
    session.add_all([student_role, user])
    await session.flush()
    session.add(TelegramAccount(user_id=user.id, telegram_id=100500, username="faq_student"))
    await session.commit()

    async def fake_llm_reply(**kwargs):
        return None

    monkeypatch.setattr(faq_ai, "_generate_llm_reply", fake_llm_reply)

    reply = await faq_ai.generate_assistant_reply(session, telegram_id=100500, message="telegram")

    assert "mini app" in reply["message"].lower()
    assert reply["used_faq_ids"]
    assert reply["status"] == "linked"
