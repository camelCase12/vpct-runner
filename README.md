# VPCT runner

[Visual Physics Comprehension Test Leaderboard](https://cbrower.dev/vpct) · [VPCT-1 dataset](https://huggingface.co/datasets/camelCase12/vpct-1) · [VPCT-redux dataset](https://huggingface.co/datasets/camelCase12/vpct-redux)

Benchmark runner for VPCT: each problem is an image of a ball, ramps and three buckets; the model predicts which bucket the ball lands in. Two sets of 100 problems: `main` (VPCT-1) and `redux`.

```bash
pip install -r requirements.txt
python -m vpct download                 # data/ (vpct-1) and data-redux/ (vpct-redux)
python -m vpct models                   # every known model and its levels
python -m vpct run -n 10                # 10-problem sample per dataset, Claude matrix
python -m vpct run -m opus -l high,max  # a family / ids / levels; resumes, skips completed
python -m vpct run -m o3,gemma-4-31b-it # other providers (API keys from env)
python -m vpct run                      # the full Claude matrix (73 configs × 200 problems)
python -m vpct status                   # per-config table + projected remaining cost
python -m vpct serve                    # live dashboard at http://127.0.0.1:8765
python -m vpct export site-export       # static snapshot (images load from HuggingFace)
python -m vpct probe                    # re-verify which levels the Claude CLI delivers
```

`run` resumes: completed (dataset, model, level, problem, rep) results are skipped, failed ones retried. `--reps N` repeats, `-d main|redux` picks a set, `-j` sets concurrency.

Results are append-only JSONL in `results/<dataset>/<model>/<level>.jsonl`, one line per attempt: prediction, tokens (incl. thinking), list-price cost, provider-reported cost, latency, full response, request settings, and `by` (`$VPCT_BY`, else `git config user.name`) so runs from different people can be merged.

## Backends

| backend | models | auth |
|---|---|---|
| `claude-cli` | every current Claude model (`claude-*`) — the planned matrix | logged-in Claude Code subscription |
| `anthropic` | the same models with an `@api` suffix (`claude-opus-4-6@api`) | `ANTHROPIC_API_KEY` |
| `openai` | OpenAI (`o3`, `gpt-4.1`, …), OpenRouter (`openrouter/…`), Gemini via Google's OpenAI endpoint | `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`; `--base-url`/`--api-key` override |
| `gemini` | native Gemini REST with thinkingLevel/mediaResolution (`gemini-3.5-flash`, `gemma-4-*`) | `GEMINI_API_KEY` |

Add a model in `vpct/models.py`. CLI and `@api` results are kept apart, so the Claude Code harness and bare API calls are never pooled. `openai`/`gemini` use the same system prompt and message layout as the original runner, whose results are imported into `results/`.

## Claude levels (`claude-cli`)

Each call is `claude -p` with no tools and a one-character system prompt; the image goes in as a base64 content block over stream-json input. The CLI exposes different controls per model; `vpct/models.py` holds the matrix `probe` verified:

| models | levels |
|---|---|
| Fable 5.1, Fable 5, Opus 5.5, Sonnet 5.5, Haiku 5.5 | low · medium · high · xhigh · max (thinking can't be disabled) |
| Opus 5, Opus 4.8, Opus 4.7, Sonnet 5 | off · low · medium · high · xhigh · max |
| Opus 4.6, Sonnet 4.6 | off · low · medium · high · max (CLI clamps xhigh → high) |
| Opus 4.5 | off · low · medium · high (xhigh/max clamp to high; budget thinking) |
| Sonnet 4.5, Haiku 4.5 | off · 1k · 4k · 16k · 32k thinking budget (`--effort` ignored) |

`off` = `MAX_THINKING_TOKENS=0` with effort pinned to high.

**Audit.** CLI calls go through an in-process passthrough proxy (`vpct/audit.py`) that records the request actually sent: model, thinking config, effort, tool count, image count, and a hash of the harness text. A result whose request doesn't match its intended level is stored as `valid: false` and excluded from accuracy. Disable with `--no-audit`.

**Harness residue.** Not removable without `--bare` (API-key only): the Agent SDK identity line prepended to the system prompt, an environment block (cwd, OS, model, date), and a reminder with the account email, about 550 tokens in all. Calls run from `/tmp/vpct-cwd` so no CLAUDE.md is discovered and the block is identical across runs. When a response hits `max_tokens`, the CLI continues it with a second request; `n_requests` records this.

**Cost.** `cost_api` = list price of an equivalent bare API call (all input uncached). `cost_cli` = what the CLI reports (includes its 1h cache writes at 2×). The runner reads the 5-hour/7-day utilization from each call, pauses at `--max-5h` (default 95%) and stops launching at `--max-7d` (default 90%).
