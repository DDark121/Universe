from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

settings = get_settings()
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}


def ensure_attachments_dir() -> Path:
    root = Path(settings.attachments_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


async def save_attachment(file: UploadFile) -> tuple[str, int, str]:
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    content = await file.read()
    max_bytes = settings.attachments_max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment exceeds size limit")

    ext = Path(file.filename or "file").suffix or ".bin"
    root = await asyncio.to_thread(ensure_attachments_dir)
    path = root / f"{uuid4()}{ext}"
    await asyncio.to_thread(path.write_bytes, content)
    return str(path), len(content), file.content_type
