#!/usr/bin/env python3
from __future__ import annotations

import asyncio, json, os, sys
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Callable, Coroutine, Dict, List, Optional

from cli import parse_args
from prompt import load_prompt
from utils import extract_bucket, robust_request
from vpct_dataclasses import BenchmarkResult, PredictionResult
from model_registry import MODEL_REGISTRY

from adapters.openai_adapter  import make_openai_adapter
from adapters.claude_adapter  import make_claude_adapter

async def bench_model(
    slug: str,
    call: Callable[[Path, str], Coroutine[None, None, str]],
    *,
    sim_files: List[Path],
    prompt: str,
    runs: int,
    batch_size: int,
    max_retries: int,
    base_delay: float,
    out_dir: Path,
    overwrite: bool,
) -> None:
    """UNCHANGED except: ‘sequential’ branch already removed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    run_accs: List[float] = []

    for run_idx in range(1, runs + 1):
        run_file = out_dir / f"benchmark_results_{slug}_run{run_idx}.json"
        if run_file.exists() and not overwrite:
            with run_file.open() as fh:
                run_accs.append(json.load(fh)["overall_accuracy"])
            print(f"↪︎  skipping {run_file.name}", file=sys.stderr)
            continue

        print(f"\n▶︎  {slug} – run {run_idx}/{runs}")
        bench = BenchmarkResult(model_name=slug)

        for batch_start in range(0, len(sim_files), batch_size):
            batch_paths = sim_files[batch_start : batch_start + batch_size]

            async def process(path: Path) -> Optional[PredictionResult]:
                sim_id = int(path.stem.split("_")[1])
                png = path.with_name(f"sim_{sim_id}_initial.png")
                res_json = path.with_name(f"sim_{sim_id}_results.json")
                if not png.exists() or not res_json.exists():
                    print(f"⚠️  sim {sim_id} missing assets", file=sys.stderr)
                    return None

                actual_bucket = json.loads(res_json.read_bytes())["finalBucket"]

                text = await robust_request(
                    lambda: call(png, prompt),
                    max_retries=max_retries,
                    base_delay=base_delay,
                    label=f"{slug} sim {sim_id}",
                )
                pred = extract_bucket(text)
                return PredictionResult(
                    simulation_id=sim_id,
                    initial_image_path=str(png),
                    prompt=prompt,
                    model_response=text,
                    actual_bucket=actual_bucket,
                    predicted_bucket=pred,
                    is_correct=pred == actual_bucket,
                )

            batch_res = await asyncio.gather(*(process(p) for p in batch_paths))
            bench.predictions.extend(r for r in batch_res if r)

        tmp = run_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({**asdict(bench),
                                   "overall_accuracy": bench.overall_accuracy}, indent=2))
        tmp.replace(run_file)
        print(f"✔︎  {run_file.name}  acc={bench.overall_accuracy:.2%}")
        run_accs.append(bench.overall_accuracy)
        await asyncio.sleep(5)

    (out_dir / f"benchmark_results_{slug}_avg.json").write_text(
        json.dumps(
            {"model_name": slug,
             "run_accuracies": run_accs,
             "average_accuracy": mean(run_accs)}, indent=2)
    )
    print(f"★  {slug} avg acc = {mean(run_accs):.2%}")

async def main() -> None:
    args = parse_args()
    prompt = load_prompt(args.prompt_file)

    sims = sorted(
        p for p in args.data_dir.glob("sim_*.json")
        if not p.name.endswith("_results.json")
    )
    if not sims:
        sys.exit(f"No sim_*.json found in {args.data_dir}")

    if args.subset and args.subset > 0:
        sims = sims[: args.subset]

    requested = [m.strip() for m in (args.models or "").split(",") if m.strip()]
    unknown = [m for m in requested if m not in MODEL_REGISTRY]
    if unknown:
        sys.exit(f"Unknown model slug(s): {', '.join(unknown)}")

    adapters: Dict[str, Callable[[Path, str], Coroutine[None, None, str]]] = {}

    for slug in requested:
        cfg = MODEL_REGISTRY[slug]              # full dict: {"provider": "...", ...}
        provider = cfg["provider"]

        if provider == "openai":
            adapters[slug] = make_openai_adapter(
                model=cfg.get("model", slug),                   # "o3", "o4-mini", …
                max_tokens=args.max_tokens,
                timeout_seconds=args.timeout_seconds,
                reasoning_effort=cfg.get("reasoning_effort"),   # may be None
                api_key=args.openai_api_key or os.getenv("OPENAI_API_KEY"),
                base_url=args.openai_base_url,
            )

        elif provider == "anthropic":
            adapters[slug] = make_claude_adapter(
                model=cfg.get("model", slug),
                max_tokens=args.max_tokens,
                thinking_budget=cfg.get("thinking_budget", args.thinking_budget),
                timeout_seconds=args.timeout_seconds,
            )

        else:
            sys.exit(f"Unhandled provider '{provider}' in MODEL_REGISTRY[{slug!r}]")

    for slug, call in adapters.items():
        await bench_model(
            slug, call,
            sim_files=sims,
            prompt=prompt,
            runs=args.runs,
            batch_size=args.batch_size,
            max_retries=args.max_retries,
            base_delay=args.base_delay,
            out_dir=args.output_dir,
            overwrite=args.overwrite,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
