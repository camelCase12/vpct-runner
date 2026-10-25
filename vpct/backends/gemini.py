"""Native Gemini REST (v1alpha): thinkingLevel and mediaResolution aren't on the OpenAI layer."""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import httpx

from ..models import Level, Model

API_BASE = "https://generativelanguage.googleapis.com/v1alpha"
SYSTEM = "You are an expert physics simulator that predicts bucket outcomes."

_client: httpx.AsyncClient | None = None


async def run_one(model: Model, level: Level, image: Path, prompt: str, *, timeout: float,
                  max_tokens: int | None = None, api_key: str | None = None, **_) -> dict:
    global _client
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        return {"error": "GEMINI_API_KEY not set", "retryable": False}
    if _client is None:
        _client = httpx.AsyncClient()

    gen: dict = {}
    if level.effort:
        gen["thinkingConfig"] = {"thinkingLevel": level.effort.upper()}
    if model.media_resolution:
        gen["mediaResolution"] = f"MEDIA_RESOLUTION_{model.media_resolution.upper()}"
    mt = max_tokens or model.max_tokens
    if mt:
        gen["maxOutputTokens"] = mt
    payload = {
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(image.read_bytes()).decode()}},
            {"text": prompt},
        ]}],
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        **({"generationConfig": gen} if gen else {}),
    }
    sent = {"model": model.wire_model, "effort": level.effort, "media_resolution": model.media_resolution,
            "max_tokens": mt}
    t0 = time.monotonic()
    ms = lambda: int((time.monotonic() - t0) * 1000)
    try:
        resp = await _client.post(f"{API_BASE}/models/{model.wire_model}:generateContent",
                                  params={"key": key}, json=payload, timeout=timeout)
    except httpx.HTTPError as e:
        return {"error": f"{type(e).__name__}: {e}"[:500], "retryable": True, "ms": ms(), "sent": sent}
    if resp.status_code != 200:
        return {"error": f"api error {resp.status_code}: {resp.text}"[:500],
                "retryable": resp.status_code == 429 or resp.status_code >= 500,
                "limited": resp.status_code == 429, "ms": ms(), "sent": sent}

    data = resp.json()
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p["text"] for p in (cand.get("content") or {}).get("parts") or [] if "text" in p)
    u = data.get("usageMetadata") or {}
    think = u.get("thoughtsTokenCount", 0)
    cached = u.get("cachedContentTokenCount", 0)  # included in promptTokenCount
    return {
        "text": text,
        "tok": {"in": u.get("promptTokenCount", 0) - cached, "cache_w": 0, "cache_r": cached,
                "out": u.get("candidatesTokenCount", 0) + think, "think": think},
        "ms": ms(), "stop_reason": cand.get("finishReason"), "sent": sent,
    }
