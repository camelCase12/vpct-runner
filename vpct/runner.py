from __future__ import annotations

import asyncio
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import chain, zip_longest

from . import store
from .audit import AuditProxy
from .backends import run_one
from .backends.claude_cli import cli_version
from .datasets import Problem
from .models import Level, Model, claude_request, cost
from .prompt import PROMPT

ANSWER_RE = re.compile(r"answer\(\s*([123])\s*\)", re.I)


def extract_answer(text: str) -> int | None:
    found = ANSWER_RE.findall(text or "")
    return int(found[-1]) if found else None


def runner_id() -> str:
    if os.environ.get("VPCT_BY"):
        return os.environ["VPCT_BY"]
    try:
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=5)
        return name.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


@dataclass(frozen=True)
class Job:
    model: Model
    level: Level
    problem: Problem
    rep: int

    @property
    def tag(self) -> str:
        return f"{self.model.id.removeprefix('claude-')}/{self.level.key} {self.problem.dataset}#{self.problem.id}"


def verify(model: Model, level: Level, sent: dict | None) -> str | None:
    """Why an intercepted CLI request doesn't match the intended level, or None."""
    if sent is None:
        return "no request seen"
    want = claude_request(model, level)
    thinking = sent.get("thinking") or {"type": "disabled"}
    if sent.get("model") != model.wire_model:
        return f"model {sent.get('model')}"
    if thinking.get("type") != want["thinking"]["type"]:
        return f"thinking {thinking.get('type')}"
    if thinking.get("budget_tokens") != want["thinking"].get("budget_tokens"):
        return f"budget {thinking.get('budget_tokens')}"
    if sent.get("effort") != want["effort"]:
        return f"effort {sent.get('effort')}"
    if sent.get("n_tools"):
        return f"{sent['n_tools']} tools"
    if sent.get("n_images") != 1:
        return f"{sent.get('n_images')} images"
    return None


def sample_order(problems: list[Problem], seed: int = 0) -> list[Problem]:
    """Each dataset shuffled with a fixed seed, then interleaved.

    Every config walks the same order, so a partial run is the same random
    sample for all of them.
    """
    by_ds: dict[str, list[Problem]] = {}
    for p in sorted(problems, key=lambda p: (p.dataset, p.id)):
        by_ds.setdefault(p.dataset, []).append(p)
    for ps in by_ds.values():
        random.Random(seed).shuffle(ps)
    return [p for p in chain.from_iterable(zip_longest(*by_ds.values())) if p is not None]


def plan(models: list[Model], level_keys: set[str] | None, problems: list[Problem], *,
         reps: int = 1, limit: int | None = None, by_config: bool = False) -> list[Job]:
    order = sample_order(problems)
    if limit:
        counts: dict[str, int] = {}
        kept = []
        for p in order:
            counts[p.dataset] = counts.get(p.dataset, 0) + 1
            if counts[p.dataset] <= limit:
                kept.append(p)
        order = kept
    configs = [(m, lv) for m in models for lv in m.levels if level_keys is None or lv.key in level_keys]
    done = store.latest_ok()
    jobs = []
    for rep in range(reps):
        pairs = ((c, p) for c in configs for p in order) if by_config else ((c, p) for p in order for c in configs)
        jobs += [Job(m, lv, p, rep) for (m, lv), p in pairs if (p.dataset, m.id, lv.key, p.id, rep) not in done]
    return jobs


class Runner:
    def __init__(self, jobs: list[Job], *, concurrency: int, timeout: float, audit: bool,
                 max_5h: float, max_7d: float, **call_kw):
        uses_cli = any(j.model.backend == "claude-cli" for j in jobs)
        self.jobs = jobs
        self.concurrency = concurrency
        self.timeout = timeout
        self.audit = AuditProxy(PROMPT) if audit and uses_cli else None
        self.max_5h, self.max_7d = max_5h, max_7d
        self.call_kw = call_kw
        self.cli = cli_version() if uses_cli else None
        self.by = runner_id()
        self.rate: dict | None = None
        self.pause_until = 0.0
        self.stop = False
        self.n_done = self.n_correct = self.n_err = 0
        self.spent = 0.0
        self.t0 = time.monotonic()

    def log(self, msg: str) -> None:
        print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)

    # Claude Code usage limits

    def note_rate(self, rate: dict | None) -> None:
        if not rate:
            return
        self.rate = rate
        windows = rate.get("unifiedWindows") or {}
        five, seven = windows.get("five_hour") or {}, windows.get("seven_day") or {}
        if (seven.get("utilization") or 0) >= self.max_7d and not self.stop:
            self.stop = True
            self.log(f"7-day usage at {seven['utilization']:.0%}, launching no more jobs")
        blocked = rate.get("status") not in (None, "allowed", "allowed_warning")
        if (five.get("utilization") or 0) >= self.max_5h or blocked:
            until = (five.get("resetsAt") or rate.get("resetsAt") or time.time() + 600) + 30
            if until > self.pause_until:
                self.pause_until = until
                self.log(f"5-hour usage at {five.get('utilization', 0):.0%}, pausing until "
                         f"{datetime.fromtimestamp(until):%H:%M}")

    def usage(self) -> str:
        windows = (self.rate or {}).get("unifiedWindows") or {}
        five = (windows.get("five_hour") or {}).get("utilization")
        seven = (windows.get("seven_day") or {}).get("utilization")
        return "" if five is None or seven is None else f" · 5h {five:.0%} 7d {seven:.0%}"

    async def wait_for_window(self) -> None:
        while not self.stop and time.time() < self.pause_until:
            await asyncio.sleep(min(30, self.pause_until - time.time()))

    # jobs

    async def run_job(self, job: Job) -> None:
        tries = waits = 0
        while True:
            await self.wait_for_window()
            if self.stop:
                return
            proxy = self.audit.base_url if self.audit and job.model.backend == "claude-cli" else None
            out = await run_one(job.model, job.level, job.problem.image, PROMPT,
                                timeout=self.timeout, proxy_url=proxy, **self.call_kw)
            self.note_rate(out.get("rate"))
            calls = self.audit.pop(out["session_id"]) if self.audit and out.get("session_id") else []
            if "error" not in out:
                break
            if out.get("limited") and waits < 50:
                waits += 1
                self.pause_until = max(self.pause_until, time.time() + 120)
                self.log(f"rate limited on {job.tag}, backing off")
                continue
            tries += 1
            if out.get("retryable") and tries < 3:
                await asyncio.sleep(10 * 3 ** (tries - 1))
                continue
            break
        self.save(job, out, calls)

    def save(self, job: Job, out: dict, calls: list[dict]) -> None:
        ok = "error" not in out
        tok = out.get("tok") or {"in": 0, "cache_w": 0, "cache_r": 0, "out": 0, "think": 0}
        text = out.get("text") or ""
        pred = extract_answer(text) if ok else None
        sent, n_requests, mismatch = out.get("sent"), 1, None
        if self.audit and job.model.backend == "claude-cli":
            # the CLI may send a second request to continue a long answer; the first is the real one
            sent = next((c for c in calls if c.get("max_tokens")), calls[0] if calls else None)
            n_requests = len(calls)
            mismatch = verify(job.model, job.level, sent) if ok else None
        price = cost(job.model, tok)
        windows = (out.get("rate") or {}).get("unifiedWindows")
        rec = {
            "dataset": job.problem.dataset, "model": job.model.id, "level": job.level.key,
            "problem": job.problem.id, "rep": job.rep, "backend": job.model.backend, "by": self.by,
            "ok": ok, "error": out.get("error"),
            "answer": job.problem.answer, "pred": pred, "correct": pred == job.problem.answer,
            "valid": mismatch is None, "mismatch": mismatch,
            "tok": tok, "cost_api": None if price is None else round(price, 6), "cost_cli": out.get("cost_reported"),
            "ms": out.get("ms"), "api_ms": out.get("api_ms"), "ttft_ms": out.get("ttft_ms"),
            "stop_reason": out.get("stop_reason"), "sent": sent, "n_requests": n_requests,
            "usage": windows and {
                **{w: (windows.get(w) or {}).get("utilization") for w in ("five_hour", "seven_day")},
                **{w + "_reset": (windows.get(w) or {}).get("resetsAt") for w in ("five_hour", "seven_day")},
            },
            "cli": self.cli if job.model.backend == "claude-cli" else None,
            "session_id": out.get("session_id"),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "response": text,
        }
        store.append(rec)

        self.n_done += 1
        self.n_err += not ok
        self.n_correct += rec["correct"]
        self.spent += price or 0
        mark = "✓" if rec["correct"] else "ERR" if not ok else "?" if pred is None else "✗"
        note = f" [{mismatch or (rec['error'] or '')[:80]}]" if mismatch or rec["error"] else ""
        acc = self.n_correct / max(1, self.n_done - self.n_err)
        price_s = "$?" if price is None else f"${price:.3f}"
        self.log(f"{self.n_done}/{len(self.jobs)} {mark} {job.tag} {(rec['ms'] or 0) / 1000:.0f}s "
                 f"{tok['out']}tok {price_s} · acc {acc:.0%} · ${self.spent:.2f}{self.usage()}{note}")

    async def run(self) -> None:
        if not self.jobs:
            self.log("nothing to do")
            return
        if self.audit:
            await self.audit.start()
        cli = f" · claude {self.cli}" if self.cli else ""
        self.log(f"{len(self.jobs)} jobs · concurrency {self.concurrency}{cli}{' · audit on' if self.audit else ''}")
        queue: asyncio.Queue[Job] = asyncio.Queue()
        for job in self.jobs:
            queue.put_nowait(job)

        async def worker(i: int) -> None:
            await asyncio.sleep(i * 0.3)  # don't start every CLI process at once
            while not self.stop and not queue.empty():
                await self.run_job(queue.get_nowait())

        try:
            await asyncio.gather(*(worker(i) for i in range(self.concurrency)))
        finally:
            if self.audit:
                await self.audit.stop()
            mins = (time.monotonic() - self.t0) / 60
            self.log(f"done: {self.n_done} results ({self.n_err} errors) in {mins:.1f} min, "
                     f"${self.spent:.2f} at list price{self.usage()}")


def main_run(jobs: list[Job], **kw) -> None:
    try:
        asyncio.run(Runner(jobs, **kw).run())
    except KeyboardInterrupt:
        print("\ninterrupted; finished results are saved, rerun to resume", file=sys.stderr)
