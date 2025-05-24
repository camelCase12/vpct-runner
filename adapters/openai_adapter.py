import base64
from pathlib import Path
from typing import Callable, Coroutine, Optional

import openai

def make_openai_adapter(
    model: str,
    *,
    api_key: Optional[str],
    base_url: Optional[str],
    max_tokens: int = 4096,
    reasoning_effort: str | None = None,
    timeout_seconds: int = 600,
) -> Callable[[Path, str], Coroutine[None, None, str]]:
    """
    Build an async callable for any OpenAI-compatible endpoint.
    """

    client = openai.AsyncClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout_seconds,
    )

    async def _call(image_path: Path, prompt: str) -> str:
        img_b64 = base64.b64encode(image_path.read_bytes()).decode()
        messages = [
            {"role": "system",
             "content": "You are an expert physics simulator that predicts bucket outcomes."},
            {"role": "user",
             "content": [
                 {"type": "text", "text": prompt},
                 {"type": "image_url", "image_url": {
                     "url": f"data:image/png;base64,{img_b64}", "detail": "auto"}},
             ]},
        ]
        extra = {}
        if reasoning_effort:
            extra["reasoning_effort"] = reasoning_effort

        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,
            **extra,
        )
        return resp.choices[0].message.content

    return _call
