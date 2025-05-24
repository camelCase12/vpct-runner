import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run-vpct.py",
        description="Run image-based bucket-prediction benchmarks across OpenAI-compatible and Anthropic endpoints.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ───────── directories / prompt ────────────────────────────────────────────
    p.add_argument("-d", "--data-dir",   type=Path, default=Path("data"))
    p.add_argument("-o", "--output-dir", type=Path, default=Path("out"))
    p.add_argument("-p", "--prompt-file", type=Path, default=None)

    # ───────── model selection & repetitions ──────────────────────────────────
    p.add_argument("-m", "--models", type=str, default=None,
                   help="Comma-separated model slugs (see MODEL_REGISTRY).")
    p.add_argument("--runs",        type=int, default=1)
    p.add_argument("--batch-size",  type=int, default=1)
    p.add_argument("--subset", type=int, default=None,
                   help="Run a smaller subset of the VPCT benchmark.")

    # ───────── retry / back-off knobs ─────────────────────────────────────────
    p.add_argument("--max-retries",   type=int, default=5)
    p.add_argument("--base-delay",    type=float, default=5.0)
    p.add_argument("--overwrite",     action="store_true")

    # ───────── shared per-request limits ─────────────────────────────────────
    p.add_argument("--max-tokens",     type=int, default=4096)
    p.add_argument("--timeout-seconds", type=int, default=600)
    p.add_argument("--thinking-budget", type=int, default=16_000,
                   help="Anthropic thinking_budget (ignored by OpenAI).")

    # ───────── OpenAI-compatible endpoint options ──────────────────────
    p.add_argument("--openai-base-url", type=str, default=None,
                   help="Override base_url for OpenAI-compatible endpoints "
                        "(e.g. https://openrouter.ai/api/v1).")
    p.add_argument("--openai-api-key",  type=str, default=None,
                   help="API key for that endpoint. If omitted, falls back to "
                        "OPENAI_API_KEY env var.")

    return p.parse_args()
