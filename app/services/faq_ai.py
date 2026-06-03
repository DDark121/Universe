from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import get_redis_client
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.enums import BindingRequestStatus
from app.db.models import TelegramAccount, TelegramBindingRequest, User

settings = get_settings()
logger = get_logger(__name__)

_FAQ_NAMESPACE = UUID("c8e0a904-f088-4a18-a4c4-bc5afbe1cc0e")
_DEFAULT_CATEGORY = "general"
_CHUNK_SIZE = 1_200
_CHUNK_OVERLAP = 200


def _prepare_offline_embedding_env() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _ensure_directory(preferred: Path, fallback: Path, label: str) -> Path:
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "faq_storage_fallback_enabled",
            target=label,
            preferred=str(preferred),
            fallback=str(fallback),
        )
        return fallback


@dataclass(slots=True)
class AssistantFaqContext:
    item_id: UUID
    category_id: UUID
    category_name: str
    question: str
    answer: str
    keywords: str
    source_path: str

    @property
    def text(self) -> str:
        return (
            f"Категория: {self.category_name}\n"
            f"Вопрос: {self.question}\n"
            f"Ответ: {self.answer}\n"
            f"Ключевые слова: {self.keywords}"
        )


@dataclass(slots=True)
class AssistantUserContext:
    status: str
    full_name: str | None
    roles: list[str]
    group_code: str | None = None
    note: str | None = None


@dataclass(slots=True)
class FaqChunk:
    item: AssistantFaqContext
    chunk_index: int
    page_content: str


@lru_cache(maxsize=1)
def _faq_index_root() -> Path:
    return _ensure_directory(
        Path(settings.faq_index_dir),
        Path("/tmp/universe-faq-index"),
        "faq_index_dir",
    )


@lru_cache(maxsize=1)
def _faq_embeddings_cache_root() -> Path:
    return _ensure_directory(
        Path(settings.faq_embeddings_cache_dir),
        Path("/tmp/universe-faq-models"),
        "faq_embeddings_cache_dir",
    )


def _faq_source_root() -> Path:
    return Path(settings.faq_source_dir)


def _faq_manifest_path() -> Path:
    return _faq_index_root() / "manifest.json"


def _faq_store_dir() -> Path:
    return _faq_index_root() / "vectorstore"


def _faq_history_key(telegram_id: int) -> str:
    return f"faq_ai:history:{telegram_id}"


def _faq_vector_available() -> bool:
    if not settings.faq_assistant_enabled:
        return False
    try:
        import faiss  # noqa: F401
        import fastembed  # noqa: F401
        import langchain_community.vectorstores  # noqa: F401
    except Exception:
        return False
    return True


def _faq_llm_available() -> bool:
    if not settings.faq_assistant_enabled or not settings.openrouter_api_key:
        return False
    try:
        import langchain_openrouter  # noqa: F401
    except Exception:
        return False
    return True


def _read_markdown_file(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("faq_source_file_skipped", path=str(path), reason=str(exc))
        return None
    return content


def _faq_item_from_path(root: Path, path: Path) -> AssistantFaqContext | None:
    content = _read_markdown_file(path)
    if content is None:
        return None

    relative_path = path.relative_to(root)
    parent_path = relative_path.parent
    category_key = parent_path.as_posix() if parent_path != Path(".") else _DEFAULT_CATEGORY
    category_name = parent_path.name if parent_path != Path(".") else _DEFAULT_CATEGORY

    return AssistantFaqContext(
        item_id=uuid5(_FAQ_NAMESPACE, f"faq-item:{relative_path.as_posix()}"),
        category_id=uuid5(_FAQ_NAMESPACE, f"faq-category:{category_key}"),
        category_name=category_name,
        question=path.stem.strip(),
        answer=content,
        keywords="",
        source_path=relative_path.as_posix(),
    )


def _faq_item_sort_key(item: AssistantFaqContext) -> tuple[int, str, str]:
    return (
        0 if item.category_name == _DEFAULT_CATEGORY else 1,
        item.category_name.casefold(),
        item.question.casefold(),
    )


def load_faq_items() -> list[AssistantFaqContext]:
    root = _faq_source_root()
    if not root.exists():
        return []

    items = [
        item
        for item in (
            _faq_item_from_path(root, path)
            for path in sorted(root.rglob("*.md"), key=lambda entry: entry.relative_to(root).as_posix())
            if path.is_file()
        )
        if item is not None
    ]
    return sorted(items, key=_faq_item_sort_key)


async def load_faq_items_async() -> list[AssistantFaqContext]:
    return await asyncio.to_thread(load_faq_items)


def _faq_source_payload(items: list[AssistantFaqContext]) -> dict[str, Any]:
    payload = [
        {
            "id": str(item.item_id),
            "category_id": str(item.category_id),
            "category_name": item.category_name,
            "question": item.question,
            "answer": item.answer,
            "keywords": item.keywords,
            "source_path": item.source_path,
        }
        for item in items
    ]
    source_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "source_hash": source_hash,
        "item_count": len(items),
        "file_count": len(items),
    }


def _chunk_text(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return [""]

    chunks: list[str] = []
    start = 0
    while start < len(stripped):
        end = min(len(stripped), start + _CHUNK_SIZE)
        chunk = stripped[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(stripped):
            break
        start = max(end - _CHUNK_OVERLAP, start + 1)
    return chunks or [stripped]


def _build_faq_chunks(items: list[AssistantFaqContext]) -> list[FaqChunk]:
    chunks: list[FaqChunk] = []
    for item in items:
        for index, chunk in enumerate(_chunk_text(item.answer)):
            chunks.append(
                FaqChunk(
                    item=item,
                    chunk_index=index,
                    page_content=(
                        f"Категория: {item.category_name}\n"
                        f"Вопрос: {item.question}\n"
                        f"Ответ: {chunk}"
                    ),
                )
            )
    return chunks


def _faq_index_hash(chunks: list[FaqChunk]) -> str:
    payload = [
        {
            "item_id": str(chunk.item.item_id),
            "category_id": str(chunk.item.category_id),
            "question": chunk.item.question,
            "chunk_index": chunk.chunk_index,
            "page_content": chunk.page_content,
        }
        for chunk in chunks
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _read_manifest() -> dict[str, Any] | None:
    path = _faq_manifest_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


async def _read_manifest_async() -> dict[str, Any] | None:
    return await asyncio.to_thread(_read_manifest)


def _write_manifest(payload: dict[str, Any]) -> None:
    root = _faq_index_root()
    root.mkdir(parents=True, exist_ok=True)
    _faq_manifest_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def _write_manifest_async(payload: dict[str, Any]) -> None:
    await asyncio.to_thread(_write_manifest, payload)


def _clear_store_dir() -> None:
    shutil.rmtree(_faq_store_dir(), ignore_errors=True)


async def _clear_store_dir_async() -> None:
    await asyncio.to_thread(_clear_store_dir)


def _embedding_cache_has_files(cache_dir: Path) -> bool:
    return cache_dir.exists() and any(path.is_file() for path in cache_dir.rglob("*"))


@lru_cache(maxsize=1)
def _get_local_embeddings():
    _prepare_offline_embedding_env()

    from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

    cache_dir = _faq_embeddings_cache_root()
    if not _embedding_cache_has_files(cache_dir):
        raise RuntimeError(
            f"FAQ embedding model cache is empty in {cache_dir}. "
            "Provision the model offline before building or using the FAQ index."
        )

    return FastEmbedEmbeddings(
        model_name=settings.faq_embeddings_model,
        cache_dir=str(cache_dir),
        doc_embed_type="passage",
    )


async def ensure_faq_runtime_ready() -> dict[str, Any]:
    _faq_index_root()
    _faq_embeddings_cache_root()
    if not settings.faq_assistant_enabled:
        return {"status": "disabled"}
    if not _faq_vector_available():
        logger.warning("faq_runtime_unavailable", reason="vector_dependencies_missing")
        raise RuntimeError("FAISS/FastEmbed runtime is unavailable")
    _get_local_embeddings()
    return {"status": "ready"}


def get_faq_index_status() -> dict[str, Any]:
    root = _faq_source_root()
    items = load_faq_items()
    source = _faq_source_payload(items)
    manifest = _read_manifest() or {}
    store_exists = _faq_store_dir().exists()

    if not root.exists():
        status = "missing"
    elif not items:
        status = "empty"
    elif not manifest or not store_exists:
        status = "missing"
    elif (
        manifest.get("source_hash") != source["source_hash"]
        or manifest.get("item_count") != source["item_count"]
        or manifest.get("file_count") != source["file_count"]
    ):
        status = "stale"
    else:
        status = str(manifest.get("status", "ready"))

    return {
        "status": status,
        "assistant_enabled": settings.faq_assistant_enabled,
        "vector_runtime_available": _faq_vector_available(),
        "source_dir": str(root),
        "source_hash": source["source_hash"],
        "index_hash": manifest.get("index_hash"),
        "file_count": source["file_count"],
        "item_count": source["item_count"],
        "chunk_count": int(manifest.get("chunk_count") or 0),
        "built_at": manifest.get("built_at"),
        "model_name": settings.faq_embeddings_model,
    }


async def get_faq_index_status_async() -> dict[str, Any]:
    return await asyncio.to_thread(get_faq_index_status)


async def rebuild_faq_index() -> dict[str, Any]:
    items = await load_faq_items_async()
    status = await get_faq_index_status_async()
    base_payload = {
        "assistant_enabled": settings.faq_assistant_enabled,
        "vector_runtime_available": _faq_vector_available(),
        "source_dir": status["source_dir"],
        "source_hash": status["source_hash"],
        "file_count": status["file_count"],
        "item_count": status["item_count"],
        "model_name": settings.faq_embeddings_model,
    }

    built_at = datetime.now(UTC).isoformat()
    if not items:
        await _clear_store_dir_async()
        payload = {
            **base_payload,
            "status": "empty",
            "index_hash": None,
            "chunk_count": 0,
            "built_at": built_at,
        }
        await _write_manifest_async(payload)
        logger.info("faq_index_rebuilt", status="empty", items=0, chunks=0)
        return payload

    if not _faq_vector_available():
        raise RuntimeError("FAISS/FastEmbed runtime is unavailable")

    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document

    chunks = _build_faq_chunks(items)
    documents = [
        Document(
            page_content=chunk.page_content,
            metadata={
                "faq_item_id": str(chunk.item.item_id),
                "category_id": str(chunk.item.category_id),
                "category_name": chunk.item.category_name,
                "question": chunk.item.question,
                "answer": chunk.item.answer,
                "keywords": chunk.item.keywords,
                "source_path": chunk.item.source_path,
                "chunk_index": chunk.chunk_index,
            },
        )
        for chunk in chunks
    ]

    embeddings = _get_local_embeddings()
    await _clear_store_dir_async()
    store = await asyncio.to_thread(FAISS.from_documents, documents, embeddings)
    await asyncio.to_thread(store.save_local, str(_faq_store_dir()))

    payload = {
        **base_payload,
        "status": "ready",
        "index_hash": _faq_index_hash(chunks),
        "chunk_count": len(chunks),
        "built_at": built_at,
    }
    await _write_manifest_async(payload)
    logger.info("faq_index_rebuilt", status="ready", items=len(items), chunks=len(chunks))
    return payload


async def _load_faq_store():
    from langchain_community.vectorstores import FAISS

    embeddings = _get_local_embeddings()
    return await asyncio.to_thread(
        lambda: FAISS.load_local(
            str(_faq_store_dir()),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    )


def _score_faq_item(item: AssistantFaqContext, query: str) -> int:
    normalized_query = query.casefold()
    tokens = [token for token in normalized_query.split() if token]
    if not tokens:
        return 0

    question = item.question.casefold()
    category = item.category_name.casefold()
    answer = item.answer.casefold()
    score = 0
    for token in tokens:
        if token in question:
            score += 5
        if token in category:
            score += 3
        if token in answer:
            score += 1
    if normalized_query in f"{question}\n{category}\n{answer}":
        score += 2
    return score


def search_faq_items(
    query: str | None = None,
    *,
    category_id: UUID | None = None,
    limit: int | None = None,
) -> list[AssistantFaqContext]:
    items = load_faq_items()
    if category_id:
        items = [item for item in items if item.category_id == category_id]

    normalized_query = (query or "").strip()
    if normalized_query:
        scored = [
            (score, index, item)
            for index, item in enumerate(items)
            if (score := _score_faq_item(item, normalized_query)) > 0
        ]
        items = [item for _score, _index, item in sorted(scored, key=lambda row: (-row[0], row[1]))]

    if limit is not None:
        items = items[:limit]
    return items


async def search_faq_items_async(
    query: str | None = None,
    *,
    category_id: UUID | None = None,
    limit: int | None = None,
) -> list[AssistantFaqContext]:
    return await asyncio.to_thread(
        search_faq_items,
        query,
        category_id=category_id,
        limit=limit,
    )


def list_faq_categories() -> list[dict[str, Any]]:
    category_rows: dict[UUID, dict[str, Any]] = {}
    for item in load_faq_items():
        category_rows.setdefault(
            item.category_id,
            {
                "id": item.category_id,
                "name": item.category_name,
                "sort_order": 0,
                "is_active": True,
            },
        )

    rows = sorted(
        category_rows.values(),
        key=lambda row: (0 if row["name"] == _DEFAULT_CATEGORY else 1, str(row["name"]).casefold()),
    )
    for index, row in enumerate(rows, start=1):
        row["sort_order"] = index * 100
    return rows


async def list_faq_categories_async() -> list[dict[str, Any]]:
    return await asyncio.to_thread(list_faq_categories)


def list_faq_item_rows(
    query: str | None = None,
    *,
    category_id: UUID | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "id": item.item_id,
            "category_id": item.category_id,
            "category_name": item.category_name,
            "question": item.question,
            "answer": item.answer,
            "keywords": item.keywords,
            "is_active": True,
            "source_path": item.source_path,
        }
        for item in search_faq_items(query, category_id=category_id, limit=limit)
    ]


async def list_faq_item_rows_async(
    query: str | None = None,
    *,
    category_id: UUID | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        list_faq_item_rows,
        query,
        category_id=category_id,
        limit=limit,
    )


async def _search_faq_vector(query: str) -> list[AssistantFaqContext]:
    if not settings.faq_assistant_enabled or not _faq_vector_available():
        return await search_faq_items_async(query, limit=settings.faq_ai_top_k)

    status = await get_faq_index_status_async()
    if status["status"] != "ready":
        return await search_faq_items_async(query, limit=settings.faq_ai_top_k)

    try:
        store = await _load_faq_store()
        docs = await asyncio.to_thread(store.similarity_search, query, settings.faq_ai_top_k)
    except Exception as exc:
        logger.warning("faq_vector_search_fallback", reason=str(exc))
        return await search_faq_items_async(query, limit=settings.faq_ai_top_k)

    if not docs:
        return await search_faq_items_async(query, limit=settings.faq_ai_top_k)

    items: list[AssistantFaqContext] = []
    seen_ids: set[UUID] = set()
    for doc in docs:
        item_id = UUID(str(doc.metadata["faq_item_id"]))
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        items.append(
            AssistantFaqContext(
                item_id=item_id,
                category_id=UUID(str(doc.metadata["category_id"])),
                category_name=str(doc.metadata["category_name"]),
                question=str(doc.metadata["question"]),
                answer=str(doc.metadata["answer"]),
                keywords=str(doc.metadata.get("keywords") or ""),
                source_path=str(doc.metadata.get("source_path") or ""),
            )
        )
    return items or search_faq_items(query, limit=settings.faq_ai_top_k)


async def _read_history(telegram_id: int) -> list[dict[str, str]]:
    redis = get_redis_client()
    try:
        rows = await redis.lrange(_faq_history_key(telegram_id), 0, -1)
    except Exception:
        return []
    history: list[dict[str, str]] = []
    for row in rows:
        try:
            payload = json.loads(row)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("role") and payload.get("content"):
            history.append({"role": str(payload["role"]), "content": str(payload["content"])})
    return history


async def _append_history(telegram_id: int, role: str, content: str) -> None:
    redis = get_redis_client()
    key = _faq_history_key(telegram_id)
    payload = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    try:
        await redis.rpush(key, payload)
        await redis.ltrim(key, -settings.faq_history_max_messages, -1)
        await redis.expire(key, settings.faq_history_ttl_seconds)
    except Exception:
        return


def _fallback_response_for_status(user_ctx: AssistantUserContext) -> str:
    if user_ctx.status == "link_required":
        return (
            "Ваш Telegram еще не привязан к учетной записи. Откройте mini app из кнопки бота, "
            "укажите ФИО и группу и отправьте заявку на привязку."
        )
    if user_ctx.status == "pending":
        details = []
        if user_ctx.full_name:
            details.append(f"ФИО: {user_ctx.full_name}")
        if user_ctx.group_code:
            details.append(f"Группа: {user_ctx.group_code}")
        suffix = f" ({'; '.join(details)})" if details else ""
        return f"Заявка на привязку уже отправлена{suffix}. Дождитесь подтверждения администратора."
    if user_ctx.status == "rejected":
        return (
            "Последняя заявка была отклонена. Откройте mini app и отправьте новую заявку с корректными данными."
        )
    roles = ", ".join(user_ctx.roles) if user_ctx.roles else "student"
    return (
        f"Вы уже привязаны к системе как {roles}. Могу помочь с FAQ, регистрацией пропуска, "
        "расписанием и навигацией по боту."
    )


def _format_faq_fallback(
    message: str,
    faq_items: list[AssistantFaqContext],
    user_ctx: AssistantUserContext,
) -> str:
    if faq_items:
        top = faq_items[0]
        return (
            f"{top.answer}\n\n"
            f"Категория: {top.category_name}.\n"
            "Если нужно, уточните вопрос или откройте mini app для детальных действий."
        )
    return _fallback_response_for_status(user_ctx)


async def _load_user_context(session: AsyncSession, telegram_id: int) -> AssistantUserContext:
    account = (
        await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if account:
        user = (
            await session.execute(select(User).where(User.id == account.user_id).options(selectinload(User.roles)))
        ).scalar_one_or_none()
        if user:
            return AssistantUserContext(
                status="linked",
                full_name=user.full_name,
                roles=[role.code.value for role in user.roles],
            )

    request = (
        await session.execute(
            select(TelegramBindingRequest)
            .where(TelegramBindingRequest.telegram_id == telegram_id)
            .order_by(TelegramBindingRequest.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if request:
        status_value = (
            request.status.value
            if request.status in {BindingRequestStatus.PENDING, BindingRequestStatus.REJECTED}
            else "link_required"
        )
        return AssistantUserContext(
            status=status_value,
            full_name=request.full_name,
            roles=[],
            group_code=request.group_code,
            note=request.note,
        )

    return AssistantUserContext(status="link_required", full_name=None, roles=[])


def _assistant_prompt(user_ctx: AssistantUserContext, faq_items: list[AssistantFaqContext]) -> str:
    faq_block = "\n\n".join(f"[{index + 1}] {item.text}" for index, item in enumerate(faq_items))
    role_block = ", ".join(user_ctx.roles) if user_ctx.roles else "unlinked"
    return (
        "Ты FAQ-помощник Telegram-бота системы учета посещаемости студентов.\n"
        "Отвечай только по предоставленному FAQ-контексту, статусу привязки Telegram и доступным действиям системы.\n"
        "Не выдумывай правила университета и не обещай действий, которых в системе нет.\n"
        "Если контекст слабый или вопрос вне системы, прямо скажи, что не знаешь, и отправь пользователя в mini app или к администратору.\n"
        f"Статус пользователя: {user_ctx.status}.\n"
        f"Роли: {role_block}.\n"
        f"ФИО: {user_ctx.full_name or 'неизвестно'}.\n"
        f"Группа из заявки: {user_ctx.group_code or 'не указана'}.\n"
        "Доступный FAQ-контекст:\n"
        f"{faq_block or 'Контекст не найден.'}"
    )


async def _generate_llm_reply(
    *,
    telegram_id: int,
    message: str,
    user_ctx: AssistantUserContext,
    faq_items: list[AssistantFaqContext],
) -> str | None:
    if not _faq_llm_available():
        return None

    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_openrouter import ChatOpenRouter

    history = await _read_history(telegram_id)
    llm = ChatOpenRouter(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_api_base_url,
        model=settings.faq_assistant_model,
        temperature=0,
        timeout=settings.openrouter_timeout_seconds,
    )
    messages: list[Any] = [SystemMessage(content=_assistant_prompt(user_ctx, faq_items))]
    for item in history[-settings.faq_history_max_messages :]:
        if item["role"] == "assistant":
            messages.append(AIMessage(content=item["content"]))
        else:
            messages.append(HumanMessage(content=item["content"]))
    messages.append(HumanMessage(content=message))
    try:
        response = await llm.ainvoke(messages)
    except Exception as exc:
        logger.warning("faq_llm_reply_failed", reason=str(exc))
        return None
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content.strip()
    return None


async def generate_assistant_reply(
    session: AsyncSession,
    *,
    telegram_id: int,
    message: str,
) -> dict[str, Any]:
    message = message.strip()
    user_ctx = await _load_user_context(session, telegram_id)
    faq_items = await _search_faq_vector(message)

    reply = await _generate_llm_reply(
        telegram_id=telegram_id,
        message=message,
        user_ctx=user_ctx,
        faq_items=faq_items,
    )
    if not reply:
        reply = _format_faq_fallback(message, faq_items, user_ctx)

    await _append_history(telegram_id, "user", message)
    await _append_history(telegram_id, "assistant", reply)
    return {
        "message": reply,
        "used_faq_ids": [item.item_id for item in faq_items],
        "status": user_ctx.status,
    }
