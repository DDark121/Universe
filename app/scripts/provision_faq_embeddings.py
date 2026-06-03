from __future__ import annotations

import json
import sys
from pathlib import Path

from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

from app.core.logging import configure_logging, get_logger
from app.services.faq_ai import _faq_embeddings_cache_root, settings

logger = get_logger(__name__)


def _file_count(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file())


def main() -> int:
    configure_logging()
    cache_dir = _faq_embeddings_cache_root()
    try:
        embeddings = FastEmbedEmbeddings(
            model_name=settings.faq_embeddings_model,
            cache_dir=str(cache_dir),
            doc_embed_type="passage",
        )
        vector = embeddings.embed_query("ТГТУ расписание студента и FAQ")
    except Exception as exc:
        logger.exception("faq_embedding_cache_provision_failed")
        print(str(exc), file=sys.stderr)
        return 1

    payload = {
        "status": "ready",
        "model_name": settings.faq_embeddings_model,
        "cache_dir": str(cache_dir),
        "dimension": len(vector),
        "file_count": _file_count(cache_dir),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
