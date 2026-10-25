from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from . import datasets, models


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="vpct")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="fetch datasets from HuggingFace")
    d.add_argument("-d", "--datasets", default="all")

    sub.add_parser("models", help="list models and their levels")

    r = sub.add_parser("run", help="run benchmark jobs; completed ones are skipped")
    r.add_argument("-m", "--models", default="all", help="all | family | ids, comma-separated")
    r.add_argument("-l", "--levels", default="all", help="e.g. off,low,high,4k")
    r.add_argument("-d", "--datasets", default="all", help="all | main | redux")
    r.add_argument("-n", "--limit", type=int, help="problems per dataset (same sample for every config)")
    r.add_argument("--problems", help="problem ids, comma-separated")
    r.add_argument("--reps", type=int, default=1)
    r.add_argument("--by-config", action="store_true", help="finish each config before the next")
    r.add_argument("-j", "--concurrency", type=int, default=8)
    r.add_argument("--timeout", type=float, default=3600, help="seconds per call")
    r.add_argument("--max-5h", type=float, default=0.95, help="pause at this 5-hour usage")
    r.add_argument("--max-7d", type=float, default=0.90, help="stop at this 7-day usage")
    r.add_argument("--no-audit", action="store_true", help="don't intercept CLI requests")
    r.add_argument("--use-api-key", action="store_true", help="let claude -p use ANTHROPIC_API_KEY")
    r.add_argument("--max-tokens", type=int, help="API backends: output cap")
    r.add_argument("--base-url", help="openai backend: endpoint URL")
    r.add_argument("--api-key", help="openai/gemini backends: key")
    r.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("status", help="per-config summary")
    s.add_argument("-d", "--datasets", default="all")

    p = sub.add_parser("probe", help="check which levels the CLI delivers")
    p.add_argument("-m", "--models", default="all")
    p.add_argument("-j", "--concurrency", type=int, default=12)

    v = sub.add_parser("serve", help="live dashboard")
    v.add_argument("--port", type=int, default=8765)

    e = sub.add_parser("export", help="static dashboard snapshot")
    e.add_argument("out", type=Path, nargs="?", default=Path("site-export"))
    return ap.parse_args()


def run(a: argparse.Namespace) -> None:
    from .runner import main_run, plan

    problems = [p for k in datasets.resolve(a.datasets) for p in datasets.load(k)]
    if a.problems:
        ids = {int(x) for x in a.problems.split(",")}
        problems = [p for p in problems if p.id in ids]
    levels = None if a.levels == "all" else {s.strip() for s in a.levels.split(",")}
    jobs = plan(models.resolve(a.models), levels, problems, reps=a.reps, limit=a.limit, by_config=a.by_config)
    if a.dry_run:
        for (model, level), n in Counter((j.model.id, j.level.key) for j in jobs).items():
            print(f"{model:34} {level:8} {n}")
        print(f"{len(jobs)} jobs")
        return
    main_run(jobs, concurrency=a.concurrency, timeout=a.timeout, audit=not a.no_audit,
             max_5h=a.max_5h, max_7d=a.max_7d, use_api_key=a.use_api_key,
             max_tokens=a.max_tokens, base_url=a.base_url, api_key=a.api_key)


def status(a: argparse.Namespace) -> None:
    from .aggregate import build

    data = build()
    want = set(datasets.resolve(a.datasets))
    order = {m.id: i for i, m in enumerate(models.MODELS)}
    cells = sorted((c for c in data["cells"] if c["dataset"] in want),
                   key=lambda c: (c["dataset"], order[c["model"]], c["level"]))

    def num(v, spec):
        return "–".rjust(len(format(0, spec))) if v is None else format(v, spec)

    print(f"{'set':6} {'model':34} {'level':8} {'n':>4} {'acc':>6} {'95% CI':>13} "
          f"{'out tok':>8} {'think':>7} {'$/prob':>7} {'s/prob':>6}")
    for c in cells:
        print(f"{c['dataset']:6} {c['model']:34} {c['level']:8} {c['n']:4} {c['acc']:6.1%} "
              f"{c['lo']:6.1%}–{c['hi']:5.1%} {num(c['tok_out'], '8.0f')} {num(c['tok_think'], '7.0f')} "
              f"{num(c['cost'], '7.4f')} {num(c['ms'] and c['ms'] / 1000, '6.1f')}"
              + (f"  invalid {c['n_invalid']} {c['mismatch']}" if c["n_invalid"] else ""))
    pr = data["projection"]
    line = f"\nremaining {pr['remaining']} jobs · ~${pr['cost_api']} list"
    if pr["seven_day_pct"]:
        line += f" · ~{pr['seven_day_pct']}% of the 7-day window"
    if pr["unknown"]:
        line += f" · {pr['unknown']} jobs not yet priced"
    print(line)


def main() -> None:
    a = parse_args()
    if a.cmd == "download":
        for k in datasets.resolve(a.datasets):
            datasets.download(datasets.DATASETS[k])
            print(f"{k}: {len(datasets.load(k))} problems in {datasets.DATASETS[k].dir}")
    elif a.cmd == "models":
        for m in models.MODELS:
            print(f"{m.id:34} {m.backend:10} {', '.join(l.key for l in m.levels)}")
    elif a.cmd == "run":
        run(a)
    elif a.cmd == "status":
        status(a)
    elif a.cmd == "probe":
        from .probe import main_probe
        main_probe(models.resolve(a.models), a.concurrency)
    elif a.cmd == "serve":
        from .serve import main_serve
        main_serve(a.port)
    elif a.cmd == "export":
        from .serve import main_export
        main_export(a.out)


if __name__ == "__main__":
    main()
