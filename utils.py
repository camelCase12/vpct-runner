import re, sys, asyncio
from typing import Optional, Callable, Coroutine

import httpx

BUCKET_RE = re.compile(r"answer\((\d)\)", re.I)

def extract_bucket(text: str) -> Optional[int]:
    m = BUCKET_RE.search(text)
    if m:
        b = int(m.group(1))
        if b in (1, 2, 3):
            return b
    return None

async def robust_request(
    func: Callable[[], Coroutine[None, None, str]],
    *,
    max_retries: int,
    base_delay: float,
    label: str = "",
) -> str:
    """
    Wrap async request, retrying on common transient failures.
    """
    for attempt in range(max_retries):
        try:
            return await func()
        except (httpx.HTTPStatusError, httpx.ReadTimeout, httpx.ConnectError) as e:
            is_last = attempt == max_retries - 1
            delay = base_delay * 2**attempt
            msg = f"{label} – {type(e).__name__} ({attempt+1}/{max_retries})"
            if is_last:
                raise RuntimeError(msg) from e
            else:
                print(msg + f", retrying in {delay:.1f}s …", file=sys.stderr)
                await asyncio.sleep(delay)
    
    raise RuntimeError(f"{label}: exceeded retries")