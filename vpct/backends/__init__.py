"""Each backend's run_one returns a dict with text, tok, ms, stop_reason and sent,
or error/retryable/limited when the call failed. They don't raise for API errors."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

from ..models import Level, Model

MODULES = {"claude-cli": "claude_cli", "anthropic": "anthropic_api", "openai": "openai_compat", "gemini": "gemini"}


async def run_one(model: Model, level: Level, image: Path, prompt: str, **kwargs) -> dict:
    backend = import_module(f".{MODULES[model.backend]}", __name__)
    return await backend.run_one(model, level, image, prompt, **kwargs)
