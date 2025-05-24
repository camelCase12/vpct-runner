# Introduction

[Visual Physics Comprehension Test Leaderboard](https://cbrower.dev/vpct)

This is the benchmark runner code for the visual physics comprehension test (VPCT). To run the benchmark, execute run-vpct.py with options specified below. You'll need to acquire a VPCT dataset and place it in the data directory that you feed to the runner--VPCT datasets will be linked here once published (I have not yet publicly published any VPCT data).

## Usage

Check ```python model_registry.py``` to see a list of configured model slugs.

```
usage: run-vpct.py [-h] [-d DATA_DIR] [-o OUTPUT_DIR] [-p PROMPT_FILE] [-m MODELS] [--runs RUNS] [--batch-size BATCH_SIZE] [--subset SUBSET] [--max-retries MAX_RETRIES] [--base-delay BASE_DELAY] [--overwrite] [--max-tokens MAX_TOKENS] [--timeout-seconds TIMEOUT_SECONDS] [--thinking-budget THINKING_BUDGET] [--openai-base-url OPENAI_BASE_URL] [--openai-api-key OPENAI_API_KEY]

Run image-based bucket-prediction benchmarks across OpenAI-compatible and Anthropic endpoints.
```

### options:
- `-h, --help` - show this help message and exit
- `-d DATA_DIR, --data-dir DATA_DIR`
- `-o OUTPUT_DIR, --output-dir OUTPUT_DIR`
- `-p PROMPT_FILE, --prompt-file PROMPT_FILE`
- `-m MODELS, --models MODELS` - Comma-separated model slugs (see MODEL_REGISTRY). (default: None)
- `--runs RUNS`
- `--batch-size BATCH_SIZE`
- `--subset SUBSET` - Run a smaller subset of the VPCT benchmark. (default: None)
- `--max-retries MAX_RETRIES`
- `--base-delay BASE_DELAY`
- `--overwrite`
- `--max-tokens MAX_TOKENS`
- `--timeout-seconds TIMEOUT_SECONDS`
- `--thinking-budget THINKING_BUDGET` - Anthropic thinking_budget (ignored by OpenAI). (default: 0)
- `--openai-base-url OPENAI_BASE_URL` - Override base_url for OpenAI-compatible endpoints (e.g. https://openrouter.ai/api/v1). (default: None)
- `--openai-api-key OPENAI_API_KEY` - API key for that endpoint. If omitted, falls back to OPENAI_API_KEY env var. (default: None)

### Example:

```bash
python run-vpct.py -d ./data -o ./runs/gpt-4o-mini-test-subset -m gpt-4o-mini --runs 1 --batch-size 5 --max-tokens 16384 --subset 5
```

Or for a 3rd party with an openai compatibility layer:

```bash
python run-vpct.py -d ./data -o ./runs/gemini-flash-test -m gemini-2.0-flash --runs 1 --batch-size 5 --max-tokens 4096 --subset 5 --openai-base-url https://generativelanguage.googleapis.com/v1beta/openai/ --openai-api-key $GEMINI_API_KEY
```