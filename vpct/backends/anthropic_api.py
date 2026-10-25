"""Claude straight through the Anthropic API, with the request settings the CLI sends."""
from __future__ import annotations

import base64
import time
from pathlib import Path

import anthropic

from ..models import Level, Model, claude_request

_client: anthropic.AsyncAnthropic | None = None


def _get() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(max_retries=0)  # the runner owns retries
    return _client


async def run_one(model: Model, level: Level, image: Path, prompt: str, *,
                  timeout: float, max_tokens: int | None = None, **_) -> dict:
    req = claude_request(model, level)
    b64 = base64.b64encode(image.read_bytes()).decode()
    mt = max_tokens or model.max_tokens or 32000
    sent = {"model": model.wire_model, "thinking": req["thinking"], "effort": req["effort"], "max_tokens": mt}
    t0 = time.monotonic()
    ms = lambda: int((time.monotonic() - t0) * 1000)
    try:
        async with _get().messages.stream(
            model=model.wire_model, max_tokens=mt, thinking=req["thinking"], timeout=timeout,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt},
            ]}],
            extra_body={"output_config": {"effort": req["effort"]}} if req["effort"] else None,
            extra_headers={"anthropic-beta": "thinking-token-count-2026-05-13"},
        ) as stream:
            msg = await stream.get_final_message()
    except anthropic.RateLimitError as e:
        return {"error": f"api error 429: {e.message}"[:500], "retryable": True, "limited": True, "ms": ms(), "sent": sent}
    except anthropic.APIStatusError as e:
        return {"error": f"api error {e.status_code}: {e.message}"[:500],
                "retryable": e.status_code >= 500, "ms": ms(), "sent": sent}
    except anthropic.APIConnectionError as e:
        return {"error": f"{type(e).__name__}: {e}"[:500], "retryable": True, "ms": ms(), "sent": sent}

    u = msg.usage.model_dump()
    return {
        "text": "".join(b.text for b in msg.content if b.type == "text"),
        "tok": {"in": u.get("input_tokens") or 0,
                "cache_w": u.get("cache_creation_input_tokens") or 0,
                "cache_r": u.get("cache_read_input_tokens") or 0,
                "out": u.get("output_tokens") or 0,
                "think": (u.get("output_tokens_details") or {}).get("thinking_tokens") or 0},
        "ms": ms(), "stop_reason": msg.stop_reason, "sent": sent,
    }
