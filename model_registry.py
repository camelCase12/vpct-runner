from typing import Dict, Any

MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ----- OpenAI
    "gpt-4o-mini": {
        "provider": "openai",
        "model": "gpt-4o-mini",
    },
    "gpt-4o": {
        "provider": "openai",
        "model": "gpt-4o",
    },
    "gpt-4.1": {
        "provider": "openai",
        "model": "gpt-4.1",
    },
    "gpt-4.1-mini": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
    },
    "o1-pro-low": {
        "provider": "openai",
        "model": "o1-pro",
        "reasoning_effort": "low",
    },
    "o1-pro-medium": {
        "provider": "openai",
        "model": "o1-pro",
        "reasoning_effort": "medium",
    },
    "o1-pro-high": {
        "provider": "openai",
        "model": "o1-pro",
        "reasoning_effort": "high",
    },
    "o1-low": {
        "provider": "openai",
        "model": "o1",
        "reasoning_effort": "low",
    },
    "o1-medium": {
        "provider": "openai",
        "model": "o1",
        "reasoning_effort": "medium",
    },
    "o1-high": {
        "provider": "openai",
        "model": "o1",
        "reasoning_effort": "high",
    },
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
    "o3-mini-low": {
        "provider": "openai",
        "model": "o3-mini",
        "reasoning_effort": "low",
    },
    "o3-mini-medium": {
        "provider": "openai",
        "model": "o3-mini",
        "reasoning_effort": "medium",
    },
    "o3-mini-high": {
        "provider": "openai",
        "model": "o3-mini",
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

    # ----- Anthropic

    "claude-3-5-sonnet-20241022": {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
    },

    "claude-3-7-sonnet-20250219": {
        "provider": "anthropic",
        "model": "claude-3-7-sonnet-20250219",
    },
    "claude-3-7-sonnet-20250219-16k": {
        "provider": "anthropic",
        "model": "claude-3-7-sonnet-20250219",
        "thinking_budget": 16000,
    },
    "claude-3-7-sonnet-20250219-32k": {
        "provider": "anthropic",
        "model": "claude-3-7-sonnet-20250219",
        "thinking_budget": 32000,
    },
    "claude-4-sonnet-20250514-16k": {
        "provider": "anthropic",
        "model": "claude-4-sonnet-20250514",
        "thinking_budget": 16000,
    },
    "claude-4-sonnet-20250514-32k": {
        "provider": "anthropic",
        "model": "claude-4-sonnet-20250514",
        "thinking_budget": 32000,
    },

    "claude-4-sonnet-20250514": {
        "provider": "anthropic",
        "model": "claude-4-sonnet-20250514",
    },
    "claude-4-sonnet-20250514-16k": {
        "provider": "anthropic",
        "model": "claude-4-sonnet-20250514",
        "thinking_budget": 16000,
    },
    "claude-4-sonnet-20250514-32k": {
        "provider": "anthropic",
        "model": "claude-4-sonnet-20250514",
        "thinking_budget": 32000,
    },

    "claude-4-opus-20250514": {
        "provider": "anthropic",
        "model": "claude-4-opus-20250514",
    },
    "claude-4-opus-20250514-16k": {
        "provider": "anthropic",
        "model": "claude-4-opus-20250514",
        "thinking_budget": 16000,
    },

    # ----- Google

    "gemini-2.0-flash": {
        "provider": "openai",
        "model":    "gemini-2.0-flash",
    },
    "gemini-2.0-flash-thinking-exp-01-21": {
        "provider": "openai",
        "model":    "gemini-2.0-flash-thinking-exp-01-21",
    },
    "gemini-2.5-pro-preview-05-06": {
        "provider": "openai",
        "model":    "gemini-2.5-pro-preview-05-06",
    },
    "gemini-2.5-flash-preview-05-20": {
        "provider": "openai",
        "model":    "gemini-2.5-flash-preview-05-20",
    },
}