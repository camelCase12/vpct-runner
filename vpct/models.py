from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

# Matrix columns. "default" means no reasoning setting is sent.
SLOTS = ("default", "off", "low", "medium", "high", "xhigh", "max")
_S = {k: i for i, k in enumerate(SLOTS)}


@dataclass(frozen=True)
class Level:
    key: str
    slot: int
    effort: Optional[str]      # effort / reasoning_effort / thinkingLevel
    mtt: Optional[int] = None  # Claude thinking budget; 0 = thinking off


DEFAULT = Level("default", _S["default"], None)
OFF = Level("off", _S["off"], "high", 0)
EFFORT = {k: Level(k, _S[k], k) for k in ("low", "medium", "high", "xhigh", "max")}
BUDGET = {
    "1k": Level("1k", _S["low"], None, 1024),
    "4k": Level("4k", _S["medium"], None, 4096),
    "16k": Level("16k", _S["high"], None, 16384),
    "32k": Level("32k", _S["max"], None, 31999),
}
LEVELS = {"default": DEFAULT, "off": OFF, **EFFORT, **BUDGET}


@dataclass(frozen=True)
class Model:
    id: str
    family: str
    version: str
    price_in: Optional[float]   # $/MTok
    price_out: Optional[float]
    levels: tuple[Level, ...]
    backend: str = "claude-cli"  # claude-cli | anthropic | openai | gemini
    api_model: Optional[str] = None
    thinking: str = "adaptive"   # Claude only: adaptive | budget
    endpoint: Optional[str] = None
    max_tokens: Optional[int] = None
    media_resolution: Optional[str] = None
    planned: bool = False        # in the default `run` matrix

    @property
    def label(self) -> str:
        return f"{self.family} {self.version}"

    @property
    def wire_model(self) -> str:
        return self.api_model or self.id


def _levels(*keys: str) -> tuple[Level, ...]:
    return tuple(LEVELS[k] for k in keys)


FIVE = ("low", "medium", "high", "xhigh", "max")
OFF_FIVE = ("off", *FIVE)
NO_XHIGH = ("off", "low", "medium", "high", "max")
BUDGETS = ("off", "1k", "4k", "16k", "32k")


def _claude(id, family, version, price_in, price_out, levels, max_tokens, thinking="adaptive"):
    return Model(id, family, version, price_in, price_out, _levels(*levels),
                 thinking=thinking, max_tokens=max_tokens, planned=True)


# The levels the CLI actually sends for each model (check with `vpct probe`). Some
# models ignore --effort, and some quietly turn xhigh or max into high.
CLAUDE = (
    _claude("claude-fable-5-1", "Fable", "5.1", 10, 50, FIVE, 64000),
    _claude("claude-fable-5", "Fable", "5", 10, 50, FIVE, 64000),
    _claude("claude-opus-5-5", "Opus", "5.5", 4, 20, FIVE, 128000),
    _claude("claude-opus-5", "Opus", "5", 5, 25, OFF_FIVE, 64000),
    _claude("claude-opus-4-8", "Opus", "4.8", 5, 25, OFF_FIVE, 64000),
    _claude("claude-opus-4-7", "Opus", "4.7", 5, 25, OFF_FIVE, 64000),
    _claude("claude-opus-4-6", "Opus", "4.6", 5, 25, NO_XHIGH, 64000),
    _claude("claude-opus-4-5", "Opus", "4.5", 5, 25, ("off", "low", "medium", "high"), 32000, "budget"),
    _claude("claude-sonnet-5-5", "Sonnet", "5.5", 2, 10, FIVE, 128000),
    _claude("claude-sonnet-5", "Sonnet", "5", 2, 10, OFF_FIVE, 64000),
    _claude("claude-sonnet-4-6", "Sonnet", "4.6", 3, 15, NO_XHIGH, 32000),
    _claude("claude-sonnet-4-5", "Sonnet", "4.5", 3, 15, BUDGETS, 32000, "budget"),
    _claude("claude-haiku-5-5", "Haiku", "5.5", 0.10, 0.50, FIVE, 128000),
    _claude("claude-haiku-4-5", "Haiku", "4.5", 1, 5, BUDGETS, 32000, "budget"),
)

CLAUDE_API = tuple(
    replace(m, id=m.id + "@api", version=m.version + " API", backend="anthropic", api_model=m.id, planned=False)
    for m in CLAUDE
)


def _openai(id, family, version, price_in=None, price_out=None, levels=("default",), endpoint="openai"):
    return Model(id, family, version, price_in, price_out, _levels(*levels), backend="openai",
                 endpoint=endpoint, max_tokens=32000)


def _gemini(id, family, version, price_in=None, price_out=None):
    return Model(id, family, version, price_in, price_out, _levels("high"), backend="gemini",
                 media_resolution="high")


LMH = ("low", "medium", "high")
OTHER = (
    _openai("o1-pro", "OpenAI", "o1-pro", 150, 600, LMH),
    _openai("o1", "OpenAI", "o1", 15, 60, LMH),
    _openai("o3", "OpenAI", "o3", 2, 8, LMH),
    _openai("o3-mini", "OpenAI", "o3-mini", 1.1, 4.4, LMH),
    _openai("o4-mini", "OpenAI", "o4-mini", 1.1, 4.4, LMH),
    _openai("gpt-4.1", "OpenAI", "GPT-4.1", 2, 8),
    _openai("gpt-4.1-mini", "OpenAI", "GPT-4.1 mini", 0.4, 1.6),
    _openai("gpt-4o", "OpenAI", "GPT-4o", 2.5, 10),
    _openai("gpt-4o-mini", "OpenAI", "GPT-4o mini", 0.15, 0.6),
    _gemini("gemini-3.5-flash", "Gemini", "3.5 Flash"),
    _gemini("gemini-robotics-er-1.6-preview", "Gemini", "Robotics-ER 1.6", 0.0, 0.0),
    _openai("gemini-2.5-pro-preview-05-06", "Gemini", "2.5 Pro", endpoint="google"),
    _openai("gemini-2.5-flash-preview-05-20", "Gemini", "2.5 Flash", endpoint="google"),
    _openai("gemini-2.0-flash-thinking-exp-01-21", "Gemini", "2.0 Flash Thinking", endpoint="google"),
    _openai("gemini-2.0-flash", "Gemini", "2.0 Flash", 0.1, 0.4, endpoint="google"),
    _gemini("gemma-4-31b-it", "Gemma", "4 31B"),
    _gemini("gemma-4-26b-a4b-it", "Gemma", "4 26B A4B"),
    _openai("openrouter/healer-alpha", "OpenRouter", "healer-alpha", endpoint="openrouter"),
    _openai("openrouter/hunter-alpha", "OpenRouter", "hunter-alpha", endpoint="openrouter"),
)

MODELS = CLAUDE + CLAUDE_API + OTHER
BY_ID = {m.id: m for m in MODELS}
FAMILIES = tuple(dict.fromkeys(m.family for m in MODELS))


def resolve(spec: str) -> list[Model]:
    """Comma-separated: 'all' (the Claude matrix), a family, or ids ('opus-4-6' works too)."""
    families = {f.lower(): f for f in FAMILIES}
    out: list[Model] = []
    for tok in filter(None, (t.strip() for t in spec.split(","))):
        if tok == "all":
            out += [m for m in MODELS if m.planned]
        elif tok.lower() in families:
            ms = [m for m in MODELS if m.family == families[tok.lower()]]
            out += [m for m in ms if m.planned] or ms
        elif tok in BY_ID or f"claude-{tok}" in BY_ID:
            out.append(BY_ID.get(tok) or BY_ID[f"claude-{tok}"])
        else:
            raise SystemExit(f"unknown model {tok!r}")
    return list({m.id: m for m in out}.values())


def claude_request(model: Model, level: Level) -> dict:
    """The thinking/effort settings a Claude request should carry for this level."""
    if level.mtt == 0:
        thinking = {"type": "disabled"}
    elif model.thinking == "budget":
        thinking = {"type": "enabled", "budget_tokens": level.mtt or 31999}
    else:
        thinking = {"type": "adaptive"}
    # these older models reject effort, except Opus 4.5
    effort = None if model.thinking == "budget" and model.wire_model != "claude-opus-4-5" else level.effort
    return {"thinking": thinking, "effort": effort}


def cost(model: Model, tok: dict | None) -> float | None:
    """List price of the call with all input billed uncached."""
    if not tok or model.price_in is None or model.price_out is None:
        return None
    tokens_in = tok.get("in", 0) + tok.get("cache_w", 0) + tok.get("cache_r", 0)
    return (tokens_in * model.price_in + tok.get("out", 0) * model.price_out) / 1e6
