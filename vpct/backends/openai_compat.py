"""Any OpenAI-compatible chat-completions endpoint: OpenAI, OpenRouter, Google's OpenAI layer."""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import openai

from ..models import Level, Model

ENDPOINTS = {
    "openai": (None, "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "google": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
}
SYSTEM ="You are an expert physics simulator that predicts bucket outcomes."

_clients: dict[tuple, openai.AsyncOpenAI] = {}


async def run_one(model: Model, level: Level, image: Path, prompt: str, *, timeout: float,
                  max_tokens: int | None = None, base_url: str | None = None,
                  api_key: str | None = None, **_) -> dict:
    default_base, key_env = ENDPOINTS[model.endpoint or "openai"]
    base, key = base_url or default_base, api_key or os.getenv(key_env)
    if not key:
        return {"error": f"{key_env} not set", "retryable": False}
    client = _clients.get((base, key))
    if client is None:
        client = _clients[(base, key)] = openai.AsyncOpenAI(api_key=key, base_url=base, max_retries=0)

    b64 = base64.b64encode(image.read_bytes()).decode()
    mt = max_tokens or model.max_tokens
    extra = {"reasoning_effort": level.effort} if level.effort else {}
    sent = {"model": model.wire_model, "endpoint": base or "openai", "effort": level.effort, "max_tokens": mt}
    t0 = time.monotonic()
    ms = lambda: int((time.monotonic() - t0) * 1000)
    try:
        resp = await client.chat.completions.create(
            model=model.wire_model, timeout=timeout,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "auto"}},
                ]},
            ],
            **({"max_completion_tokens": mt} if mt else {}), **extra,
        )
    except openai.RateLimitError as e:
        return {"error": f"api error 429: {e.message}"[:500], "retryable": True, "limited": True, "ms": ms(), "sent": sent}
    except openai.APIStatusError as e:
        return {"error": f"api error {e.status_code}: {e.message}"[:500],
                "retryable": e.status_code >= 500, "ms": ms(), "sent": sent}
    except openai.APIConnectionError as e:
        return {"error": f"{type(e).__name__}: {e}"[:500], "retryable": True, "ms": ms(), "sent": sent}

    u = resp.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", None) or 0
    choice = resp.choices[0] if resp.choices else None
    return {
        "text": (choice.message.content if choice else None) or "",
        "tok": {"in": (u.prompt_tokens if u else 0) - cached, "cache_w": 0, "cache_r": cached,
                "out": u.completion_tokens if u else 0,
                "think": getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", None) or 0},
        "ms": ms(), "stop_reason": choice.finish_reason if choice else None,
        "cost_reported": getattr(u, "cost", None),  # OpenRouter reports this
        "sent": sent,
    }
