from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median

from . import store
from .datasets import DATASETS, load
from .models import BY_ID, MODELS, SLOTS


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, center - half), min(1.0, center + half)


def mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def tokens(rec: dict, *keys: str) -> int | None:
    t = rec.get("tok")
    return sum(t.get(k, 0) for k in keys) if t else None


def summarize_cell(recs: list[dict]) -> dict:
    valid = [r for r in recs if r.get("valid", True)]
    # average repeat runs of the same problem, so n is the number of problems
    per_problem: dict[int, list[bool]] = defaultdict(list)
    for r in valid:
        per_problem[r["problem"]].append(r["correct"])
    n = len(per_problem)
    k = sum(sum(v) / len(v) for v in per_problem.values())
    lo, hi = wilson(k, n)
    times = [r["ms"] for r in valid if r.get("ms")]
    return {
        "n": n, "attempts": len(valid), "correct": k, "acc": k / n if n else None, "lo": lo, "hi": hi,
        "n_invalid": len(recs) - len(valid),
        "mismatch": sorted({r["mismatch"] for r in recs if r.get("mismatch")}),
        "tok_in": mean(tokens(r, "in", "cache_w", "cache_r") for r in valid),
        "tok_out": mean(tokens(r, "out") for r in valid),
        "tok_think": mean(tokens(r, "think") for r in valid),
        "cost": mean(r.get("cost_api") for r in valid),
        "cost_total": sum(r.get("cost_api") or 0 for r in valid),
        "cost_cli_total": sum(r.get("cost_cli") or 0 for r in recs),
        "ms": mean(r.get("ms") for r in valid),
        "ms_p50": median(times) if times else None,
    }


def usage_rates(recs: list[dict]) -> dict:
    """CLI-reported dollars per 1% of each Claude Code usage window."""
    out = {}
    for window in ("five_hour", "seven_day"):
        by_reset: dict = defaultdict(list)
        for r in recs:
            if (r.get("usage") or {}).get(window) is not None and r.get("cost_cli") is not None:
                by_reset[r["usage"].get(window + "_reset")].append(r)
        # calls finish out of order, so compare the highest and lowest reading in each window
        pct = dollars = 0.0
        for rs in by_reset.values():
            seen = [r["usage"][window] for r in rs]
            if max(seen) > min(seen):
                pct += (max(seen) - min(seen)) * 100
                dollars += sum(r["cost_cli"] for r in rs)
        out[window] = {"dollars_per_pct": dollars / pct if pct >= 3 else None}
    return out


def projection(cells: dict[tuple, dict], problems: dict[str, list]) -> dict:
    """Remaining jobs in the planned matrix, priced from what each config has cost so far."""
    remaining = unknown = 0
    cost_api = cost_cli = 0.0
    for m in MODELS:
        if not m.planned:
            continue
        for lv in m.levels:
            measured = [c for ds in problems if (c := cells.get((ds, m.id, lv.key))) and c["attempts"]]
            for ds, ps in problems.items():
                c = cells.get((ds, m.id, lv.key))
                left = len(ps) - (c["n"] if c else 0)
                if left <= 0:
                    continue
                remaining += left
                est = c if c and c["attempts"] else (measured[0] if measured else None)
                if est is None or est["cost"] is None:
                    unknown += left
                    continue
                cost_api += left * est["cost"]
                cost_cli += left * est["cost_cli_total"] / (est["attempts"] + est["n_invalid"])
    return {"remaining": remaining, "unknown": unknown, "cost_api": round(cost_api, 2), "cost_cli": round(cost_cli, 2)}


def build(root=store.RESULTS) -> dict:
    latest = store.latest_ok(root)
    problems = {k: load(k) for k, d in DATASETS.items() if d.dir.exists()}
    position = {ds: {p.id: i for i, p in enumerate(ps)} for ds, ps in problems.items()}

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for rec in latest.values():
        if rec["model"] in BY_ID:
            groups[(rec["dataset"], rec["model"], rec["level"])].append(rec)

    cells, outcomes = {}, defaultdict(dict)
    for (ds, model, level), recs in sorted(groups.items()):
        cells[(ds, model, level)] = {"dataset": ds, "model": model, "level": level, **summarize_cell(recs)}
        if ds in position:
            # the answer given for each problem, in dataset order (0 = no answer, None = not run yet)
            preds = [None] * len(position[ds])
            for r in sorted(recs, key=lambda r: r.get("rep", 0)):
                if r.get("valid", True) and r["problem"] in position[ds]:
                    preds[position[ds][r["problem"]]] = r["pred"] or 0
            outcomes[ds][f"{model}|{level}"] = preds

    records = list(store.iter_records(root))
    with_usage = [r for r in records if (r.get("usage") or {}).get("seven_day") is not None]
    last = max(with_usage, key=lambda r: r["ts"], default=None)
    rates = usage_rates(records)
    proj = projection(cells, problems)
    per_pct = rates["seven_day"]["dollars_per_pct"]
    proj["seven_day_pct"] = round(proj["cost_cli"] / per_pct, 1) if per_pct and not proj["unknown"] else None

    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_records": len(records),
        "slots": SLOTS,
        "models": [{
            "id": m.id, "label": m.label, "family": m.family, "version": m.version,
            "thinking": m.thinking, "backend": m.backend, "planned": m.planned,
            "levels": [{"key": l.key, "slot": l.slot, "effort": l.effort, "mtt": l.mtt} for l in m.levels],
        } for m in MODELS],
        "datasets": {ds: [{"id": p.id, "answer": p.answer} for p in ps] for ds, ps in problems.items()},
        "cells": list(cells.values()),
        "outcomes": outcomes,
        "usage": last and {"five_hour": last["usage"]["five_hour"], "seven_day": last["usage"]["seven_day"]},
        "projection": proj,
    }
