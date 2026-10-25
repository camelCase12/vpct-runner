from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import time
from pathlib import Path

from ..models import Level, Model

# Run from an empty folder outside $HOME so Claude Code doesn't load CLAUDE.md, and
# always the same folder so the text Claude Code adds to each request stays the same.
WORKDIR = Path("/tmp/vpct-cwd")
SYSTEM_PROMPT = "."  # an empty prompt gets replaced by Claude Code's default one


def cli_version() -> str:
    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30).stdout.split()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return "unknown"


def env_for(level: Level, proxy_url: str | None, use_api_key: bool) -> dict:
    # Don't pass on this session's Claude Code settings (like CLAUDE_EFFORT) or API keys.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDE", "ANTHROPIC")) and k != "MAX_THINKING_TOKENS"}
    if use_api_key and "ANTHROPIC_API_KEY" in os.environ:
        env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
    if proxy_url:
        env["ANTHROPIC_BASE_URL"] = proxy_url
    if level.mtt is not None:
        env["MAX_THINKING_TOKENS"] = str(level.mtt)
    return env


def command(model: Model, level: Level) -> list[str]:
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--system-prompt", SYSTEM_PROMPT, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
           "--no-session-persistence", "--model", model.wire_model]
    if level.effort:
        cmd += ["--effort", level.effort]
    return cmd


def message(image: Path, prompt: str) -> bytes:
    b64 = base64.b64encode(image.read_bytes()).decode()
    msg = {"type": "user", "message": {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
        {"type": "text", "text": prompt},
    ]}}
    return (json.dumps(msg) + "\n").encode()


async def run_one(model: Model, level: Level, image: Path, prompt: str, *, timeout: float,
                  proxy_url: str | None = None, use_api_key: bool = False, **_) -> dict:
    WORKDIR.mkdir(exist_ok=True)
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *command(model, level), cwd=WORKDIR, env=env_for(level, proxy_url, use_api_key),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        limit=64 * 1024 * 1024)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(message(image, prompt)), timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError) as e:
        proc.kill()
        await proc.wait()
        if isinstance(e, asyncio.CancelledError):
            raise
        return {"error": f"timeout after {timeout:.0f}s", "retryable": True, "ms": int((time.monotonic() - t0) * 1000)}

    result = rate = None
    for line in stdout.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            result = event
        elif event.get("type") == "rate_limit_event":
            rate = event.get("rate_limit_info")

    out = {"ms": int((time.monotonic() - t0) * 1000), "rate": rate}
    if result is None:
        tail = (stderr.decode(errors="replace") or stdout.decode(errors="replace"))[-500:].strip()
        return {**out, "error": f"no result (exit {proc.returncode}): {tail}", "retryable": True}

    usage = result.get("usage") or {}
    out.update(
        text=result["result"] if isinstance(result.get("result"), str) else "",
        tok={"in": usage.get("input_tokens", 0),
             "cache_w": usage.get("cache_creation_input_tokens", 0),
             "cache_r": usage.get("cache_read_input_tokens", 0),
             "out": usage.get("output_tokens", 0),
             "think": (usage.get("output_tokens_details") or {}).get("thinking_tokens", 0)},
        ms=result.get("duration_ms") or out["ms"], api_ms=result.get("duration_api_ms"),
        ttft_ms=result.get("ttft_ms"), stop_reason=result.get("stop_reason"),
        cost_reported=result.get("total_cost_usd"), session_id=result.get("session_id"),
    )
    if result.get("is_error"):
        status = result.get("api_error_status")
        text = str(result.get("result", ""))[:500]
        limited = status == 429 or "limit" in text.lower()
        out.update(error=f"api error {status}: {text}", limited=limited,
                   retryable=limited or status is None or status >= 500)
    return out
