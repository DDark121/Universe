from __future__ import annotations

import asyncio
import json
import sys

from app.core.logging import configure_logging, get_logger
from app.services.faq_ai import rebuild_faq_index

logger = get_logger(__name__)


def main() -> int:
    configure_logging()
    try:
        result = asyncio.run(rebuild_faq_index())
    except Exception as exc:
        logger.exception("faq_index_build_failed")
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
