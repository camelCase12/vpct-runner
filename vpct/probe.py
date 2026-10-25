"""Check which levels the Claude CLI actually delivers; rerun after a Claude Code update."""
from __future__ import annotations

import asyncio
import json

from .audit import AuditProxy
from .backends.claude_cli import cli_version, run_one
from .datasets import load
from .models import BUDGET, EFFORT, MODELS, OFF, Model
from .runner import verify
from .store import RESULTS

PROMPT = "Reply with only: ok"


def candidates(m: Model):
    if m.thinking == "budget" and m.id != "claude-opus-4-5":
        return [OFF, *BUDGET.values()]
    return [OFF, *EFFORT.values()]


async def probe_all(models: list[Model], concurrency: int) -> list[dict]:
    audit = AuditProxy(PROMPT)
    await audit.start()
    image = load("main")[0].image
    slots = asyncio.Semaphore(concurrency)
    rows = []

    async def probe(m: Model, lv):
        async with slots:
            out = await run_one(m, lv, image, PROMPT, timeout=300, proxy_url=audit.base_url)
        calls = audit.pop(out["session_id"]) if out.get("session_id") else []
        sent = next((c for c in calls if c.get("max_tokens")), calls[0] if calls else None)
        rows.append({
            "model": m.id, "level": lv.key, "failed": "error" in out,
            "delivered": "error" not in out and verify(m, lv, sent) is None,
            "in_matrix": lv in m.levels,
            "sent": sent and {k: sent[k] for k in ("thinking", "effort", "max_tokens")},
            "reason": out.get("error") or verify(m, lv, sent),
        })

    try:
        await asyncio.gather(*(probe(m, lv) for m in models for lv in candidates(m)))
    finally:
        await audit.stop()
    return rows


def main_probe(models: list[Model], concurrency: int = 12) -> None:
    models = [m for m in models if m.backend == "claude-cli"]
    rows = asyncio.run(probe_all(models, concurrency))
    order = {m.id: i for i, m in enumerate(MODELS)}
    rows.sort(key=lambda r: (order[r["model"]], r["level"]))
    drift = 0
    for r in rows:
        sent = r["sent"] or {}
        note = ""
        if r["failed"]:
            note = f"  call failed: {r['reason'][:60]}"
        elif r["delivered"] != r["in_matrix"]:
            note = f"  DRIFT ({r['reason'] or 'delivered but not in matrix'})"
            drift += 1
        print(f"{r['model']:20} {r['level']:6} {'yes' if r['delivered'] else 'no ':3} "
              f"{json.dumps(sent.get('thinking'))} effort={sent.get('effort')}{note}")

    path = RESULTS / "_probe.json"
    saved = json.loads(path.read_text())["rows"] if path.exists() else []
    merged = {(r["model"], r["level"]): r for r in saved + rows}
    RESULTS.mkdir(exist_ok=True)
    path.write_text(json.dumps({"cli": cli_version(), "rows": list(merged.values())}, indent=1))
    print(f"\n{drift} level(s) differ from models.py" if drift else "\nmatrix matches models.py")
