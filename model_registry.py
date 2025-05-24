from typing import Dict, Any

MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "o3-low": {
        "provider": "openai",
        "model": "o3",
        "reasoning_effort": "low",
    },
    "o3-medium": {
        "provider": "openai",
        "model": "o3",
        "reasoning_effort": "medium",
    },
    "o3-high": {
        "provider": "openai",
        "model": "o3",
        "reasoning_effort": "high",
    },
    "o4-mini-low": {
        "provider": "openai",
        "model": "o4-mini",
        "reasoning_effort": "low",
    },
    "o4-mini-medium": {
        "provider": "openai",
        "model": "o4-mini",
        "reasoning_effort": "medium",
    },
    "o4-mini-high": {
        "provider": "openai",
        "model": "o4-mini",
        "reasoning_effort": "high",
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "model": "gpt-4o-mini",
    },
    "claude-4-sonnet-20250514": {
        "provider": "anthropic",
        "model": "claude-4-sonnet-20250514",
    },
    "claude-4-opus-20250514": {
        "provider": "anthropic",
        "model": "claude-4-opus-20250514",
    },
}