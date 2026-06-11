from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from app.core.config import get_settings


class OpenRouterError(RuntimeError):
    pass


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content) if content is not None else ""


async def openrouter_chat_completion(
    messages: Sequence[dict[str, str]],
    *,
    model: str,
    temperature: float = 0,
    timeout_seconds: int | float | None = None,
    max_tokens: int | None = None,
) -> str:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured")

    payload: dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    url = f"{settings.openrouter_api_base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds or settings.openrouter_timeout_seconds) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost/universe-admin",
                    "X-Title": "Universe Admin",
                },
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        raise OpenRouterError(f"OpenRouter returned {exc.response.status_code}: {body}") from exc
    except httpx.TimeoutException as exc:
        raise OpenRouterError("OpenRouter request timed out") from exc
    except httpx.HTTPError as exc:
        raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise OpenRouterError("OpenRouter returned an invalid response") from exc

    text = _message_content_to_text(content).strip()
    if not text:
        raise OpenRouterError("OpenRouter returned an empty response")
    return text
