"""Append-only JSONL results: results/<dataset>/<model>/<level>.jsonl, one line per attempt."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .datasets import ROOT

RESULTS = ROOT / "results"


def path_for(dataset: str, model: str, level: str) -> Path:
    # some ids contain a slash (openrouter/healer-alpha); replace it so the file stays one folder deep
    return RESULTS / dataset / model.replace("/", "__") / f"{level}.jsonl"


def append(rec: dict) -> None:
    p = path_for(rec["dataset"], rec["model"], rec["level"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def iter_records(root: Path = RESULTS) -> Iterator[dict]:
    for p in sorted(root.glob("*/*/*.jsonl")):
        with p.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue  # torn final line from a killed run


def key(rec: dict) -> tuple:
    return rec["dataset"], rec["model"], rec["level"], rec["problem"], rec.get("rep", 0)


def latest_ok(root: Path = RESULTS) -> dict[tuple, dict]:
    """The most recent successful attempt per (dataset, model, level, problem, rep)."""
    out: dict[tuple, dict] = {}
    for rec in iter_records(root):
        if rec.get("ok"):
            out[key(rec)] = rec
    return out
