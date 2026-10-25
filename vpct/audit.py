"""Local passthrough proxy for claude -p that records each request it forwards.

The CLI clamps some effort settings silently, so the request itself is the
record of what a result was run with. Requests are keyed by CLI session id.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import socket

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import StreamingResponse
from starlette.routing import Route

UPSTREAM = "https://api.anthropic.com"
DROP_REQUEST = {"host", "content-length", "accept-encoding", "connection"}
DROP_RESPONSE = {"content-length", "content-encoding", "transfer-encoding", "connection"}


def session_id(body: dict) -> str | None:
    try:
        return json.loads(body["metadata"]["user_id"])["session_id"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None


def harness_text(body: dict, prompt: str) -> str:
    parts = [b.get("text", "") for b in body.get("system") or [] if isinstance(b, dict)]
    for m in body.get("messages", []):
        content = m.get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
        parts += [b["text"] for b in blocks if b.get("type") == "text" and b["text"].strip() != prompt.strip()]
    # this line changes with every Claude Code version, so leave it out
    return "\n".join(l for l in "\n".join(parts).splitlines() if not l.startswith("x-anthropic-billing-header"))


def summarize(body: dict, prompt: str) -> dict:
    images = [b for m in body.get("messages", []) if isinstance(m.get("content"), list)
              for b in m["content"] if b.get("type") == "image"]
    harness = harness_text(body, prompt)
    return {
        "model": body.get("model"),
        "thinking": body.get("thinking"),
        "effort": (body.get("output_config") or {}).get("effort"),
        "max_tokens": body.get("max_tokens"),
        "n_tools": len(body.get("tools") or []),
        "n_images": len(images),
        "image_b64_len": sum(len(b.get("source", {}).get("data", "")) for b in images),
        "harness_chars": len(harness),
        "harness_hash": hashlib.sha256(harness.encode()).hexdigest()[:12],
    }


class AuditProxy:
    def __init__(self, prompt: str):
        self.prompt = prompt
        self.calls: dict[str, list[dict]] = {}
        self.port = free_port()
        self.client = httpx.AsyncClient(base_url=UPSTREAM, timeout=httpx.Timeout(3600, connect=30))
        self.server: uvicorn.Server | None = None
        self.task: asyncio.Task | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def handle(self, request):
        body = await request.body()
        if request.method == "POST" and request.url.path.endswith("/messages") and body:
            try:
                parsed = json.loads(body)
                if sid := session_id(parsed):
                    self.calls.setdefault(sid, []).append(summarize(parsed, self.prompt))
            except json.JSONDecodeError:
                pass
        headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP_REQUEST}
        upstream = self.client.build_request(request.method, request.url.path, params=request.query_params,
                                             headers=headers, content=body)
        resp = await self.client.send(upstream, stream=True)

        async def stream():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()

        headers = {k: v for k, v in resp.headers.items() if k.lower() not in DROP_RESPONSE}
        return StreamingResponse(stream(), status_code=resp.status_code, headers=headers)

    async def start(self) -> None:
        app = Starlette(routes=[Route("/{path:path}", self.handle, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])])
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning",
                                                    timeout_keep_alive=600))
        self.task = asyncio.create_task(self.server.serve())
        while not self.server.started:
            await asyncio.sleep(0.05)

    async def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
            await self.task
        await self.client.aclose()

    def pop(self, session: str) -> list[dict]:
        return self.calls.pop(session, [])


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
