import base64
from typing import Callable, Coroutine
from pathlib import Path

import anthropic

def make_claude_adapter(
    model: str, *, max_tokens: int, thinking_budget: int, timeout_seconds: int
) -> Callable[[Path, str], Coroutine[None, None, str]]:
    """
    Vision request via Anthropic Async SDK.
    """
    aclient = anthropic.AsyncAnthropic()

    async def _call(img_path: Path, prompt: str) -> str:
        b64 = base64.b64encode(img_path.read_bytes()).decode()
        resp = await aclient.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "enabled", "budget_tokens": thinking_budget} if thinking_budget > 0 else None,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            timeout=timeout_seconds,
        )
        
        return resp.content[-1].text

    return _call