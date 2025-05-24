#!/usr/bin/env python3
"""
Usage:
    python live_test.py
    python live_test.py -y           # auto-yes

Edit the MODELS list or COMMON_OPTS string as needed.
"""

from __future__ import annotations
import argparse, datetime, os, shlex, subprocess, sys
from typing import List

from model_registry import MODEL_REGISTRY

# Uncomment to test a specific set of models
MODEL_SLUGS: List[str] = [
    # "o3-low",
    # "o4-mini-medium",
    "claude-4-sonnet-20250514",
]

COMMON_OPTS = (
    "-d ./data "
    "--runs 1 "
    "--batch-size 3 "
    "--subset 3 "
    "--max-tokens 8192 "
    "--timeout-seconds 600"
)

OPENAI_DEFAULT_BASE = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
OPENAI_DEFAULT_KEY  = os.getenv("OPENAI_API_KEY")
ANTHROPIC_DEFAULT_BUDGET = 4096


def cmd_for(slug: str) -> List[str]:
    """Build the CLI command for a single model slug."""
    cfg = MODEL_REGISTRY[slug]
    provider = cfg["provider"]

    out_dir = f"./runs/live-{slug}-{datetime.date.today()}"
    cmd = f"python run-vpct.py {COMMON_OPTS} -o {out_dir} -m {slug}"

    if provider == "openai":
        base_url = OPENAI_DEFAULT_BASE
        api_key  = OPENAI_DEFAULT_KEY
        if base_url:
            cmd += f" --openai-base-url {shlex.quote(base_url)}"
        if api_key:
            cmd += f" --openai-api-key {shlex.quote(api_key)}"

    elif provider == "anthropic":
        thinking_budget = cfg.get("thinking_budget", ANTHROPIC_DEFAULT_BUDGET)
        cmd += f" --thinking-budget {thinking_budget}"

    else:
        raise ValueError(f"Unknown provider '{provider}' in MODEL_REGISTRY[{slug!r}]")

    return shlex.split(cmd)


def main() -> None:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("-y", "--yes", action="store_true",
                    help="Skip cost confirmation prompt")
    args = ap.parse_args()

    commands = [cmd_for(s) for s in MODEL_SLUGS]

    print("\n⚠️  LIVE-TOKEN WARNING – the following commands will hit real APIs:\n")
    for c in commands:
        print("  " + " ".join(shlex.quote(t) for t in c))

    if not args.yes:
        if input("\nProceed? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            sys.exit(1)
    else:
        print("--yes supplied, skipping confirmation.")

    for cmd in commands:
        print("\n▶", " ".join(shlex.quote(t) for t in cmd))
        result = subprocess.run(cmd)
        if result.returncode:
            sys.exit(result.returncode)

    print("\n✅ All live runs finished.")


if __name__ == "__main__":
    main()
