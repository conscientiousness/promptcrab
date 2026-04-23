<p align="center">
  <a href="https://github.com/conscientiousness/promptcrab/actions/workflows/ci.yml"><img src="https://github.com/conscientiousness/promptcrab/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://pypi.org/project/promptcrab/"><img src="https://img.shields.io/pypi/v/promptcrab.svg?cacheSeconds=300" alt="PyPI version" /></a>
  <a href="https://pypi.org/project/promptcrab/"><img src="https://img.shields.io/badge/python-%3E%3D3.12-blue" alt="Python >=3.12" /></a>
</p>

<h1 align="center">promptcrab</h1>

<p align="center"><strong>Keep the meaning. Trim the spell.</strong></p>

<p align="center">
  <a href="./README.md">English</a> ·
  <a href="./README.zh-TW.md">繁體中文</a> ·
  <a href="#installation">Installation</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#current-model-guidance">Model Guidance</a>
</p>

<p align="center">
  <img src="assets/promptcrab-banner.png" alt="promptcrab pixel art banner" width="80%" />
</p>

`promptcrab` is a CLI for rewriting prompts for downstream LLMs with quality-first copy editing, safer structure, lower token cost, and strict fidelity checks.

Instead of simply shortening text, it first creates a same-language canonical rewrite that makes the prompt clearer and easier for another LLM to execute. It then derives translated/compact candidates from that cleaner source, verifies them against the original prompt, checks protected literals such as URLs, IDs, keys, and numbers, and returns the safest compact version.

Requires Python 3.12 or newer.

## What It Does

- First rewrites the original prompt into a clearer same-language `canonical` candidate
- Derives clearer, more actionable `zh`, `wenyan`, and `en` candidates from that canonical source
- Optionally verifies each candidate with a dedicated judge backend
- Checks whether important literals were dropped
- Estimates token counts
- Picks the best valid candidate, prioritizing fidelity and clarity before token savings

## Supported Backends

- `minimax`: uses `MINIMAX_API_KEY` or `OPENAI_API_KEY`
- `gemini`: uses `GEMINI_API_KEY`
- `gemini_cli`: uses the local `gemini` executable and its own login/session
- `codex_cli`: uses the local `codex` executable

## Installation

If you are installing from a local checkout:

```bash
uv tool install .
```

Or install into a virtual environment:

```bash
uv pip install .
```

To see the available options:

```bash
promptcrab --help
```

## Configuration

`promptcrab` reads credentials in this order:

1. CLI flags such as `--minimax-api-key` and `--gemini-api-key`
2. Existing shell environment variables
3. `--env-file /path/to/file.env`
4. A `.env` file found by searching from the current working directory upward

This makes local project `.env` files work even when `promptcrab` is installed globally.

Example:

```dotenv
MINIMAX_API_KEY=your-key
GEMINI_API_KEY=your-key
OPENAI_API_KEY=your-key
```

Only set the variables required by the backend you actually use.

If you keep provider keys outside the project root, pass an explicit file:

```bash
promptcrab --env-file ~/.config/promptcrab/provider.env --help
```

## Quick Start

Rewrite a prompt with MiniMax through opencode:

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --prompt "Summarize this API design and keep every field name unchanged."
```

Rewrite a prompt from a file with the local Gemini CLI:

```bash
promptcrab \
  --backend gemini_cli \
  --model gemini-3-flash-preview \
  --prompt-file ./prompt.txt
```

Use a fixed judge backend instead of self-verification:

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --judge-backend codex_cli \
  --judge-model gpt-5.4 \
  --judge-codex-reasoning-effort medium \
  --prompt-file ./prompt.txt
```

Rewrite a prompt with the local Gemini CLI:

```bash
promptcrab \
  --backend gemini_cli \
  --model gemini-3-flash-preview \
  --prompt-file ./prompt.txt
```

Pipe a prompt through stdin:

```bash
cat ./prompt.txt | promptcrab --backend codex_cli --model gpt-5.4
```

## Common Usage

Show every candidate and its checks:

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --prompt-file ./prompt.txt \
  --show-all
```

Return machine-readable JSON:

```bash
promptcrab \
  --backend gemini_cli \
  --model gemini-3-flash-preview \
  --prompt-file ./prompt.txt \
  --json-output
```

Use a fixed local tokenizer for fast, deterministic token counts:

```bash
promptcrab \
  --backend codex_cli \
  --model gpt-5.4 \
  --prompt-file ./prompt.txt \
  --tokenizer o200k_base
```

Write the best prompt to a file:

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --prompt-file ./prompt.txt \
  --write-best-to ./optimized.txt
```

Optionally cap generation output if a specific provider/model needs it:

```bash
promptcrab \
  --backend gemini \
  --model gemini-3-flash-preview \
  --prompt-file ./prompt.txt \
  --max-output-tokens 4096
```

Use a non-default Codex executable path:

```bash
promptcrab \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-executable /path/to/codex \
  --prompt-file ./prompt.txt
```

## Current Model Guidance

Instead of checking in a small, stale benchmark table, `promptcrab` now ships a reproducible `promptcrab-benchmark` runner. It runs a built-in literal/format hard-case suite, pulls public web datasets, re-counts every prompt with one shared tokenizer, and evaluates rewrites with a multi-judge panel.

### Directional Snapshot

This single-judge snapshot was run on 2026-04-15 for a README-sized comparison that finishes quickly. It samples 4 MT-Bench cases and 4 IFEval cases, uses `o200k_base` as the shared tokenizer, keeps literal checks enabled, and evaluates every row with `codex_cli + gpt-5.4 (medium)` as the judge. Treat it as directional, not a final ranking; the GPT row is self-judged.

`Avg accepted token reduction` is computed only over cases where at least one candidate passed the fidelity gates.

| Rewrite backend | Judge | Sample | Pass rate (95% CI) | Avg accepted token reduction (95% CI) | Dataset pass split | Notes |
|---|---|---:|---:|---:|---|---|
| `codex_cli + gpt-5.4 (medium)` | `codex_cli + gpt-5.4 (medium)` | `8` | `6/8 = 75.0%` (`40.9-92.9%`) | `4.8%` (`-5.5-12.3%`) | MT-Bench `4/4`, IFEval `2/4` | Self-judged; most conservative compression. IFEval failures came from strict literal/verbatim constraints. |
| `opencode_cli + MiniMax-M2.7-highspeed` | `codex_cli + gpt-5.4 (medium)` | `8` | `2/8 = 25.0%` (`7.1-59.1%`) | `20.1%` (`19.2-20.9%`) | MT-Bench `2/4`, IFEval `0/4` | Highest accepted compression, but many IFEval cases failed on literal or format drift. |
| `gemini_cli + gemini-3-flash-preview` | `codex_cli + gpt-5.4 (medium)` | `8` | `4/8 = 50.0%` (`21.5-78.5%`) | `7.8%` (`-16.7-26.3%`) | MT-Bench `3/4`, IFEval `1/4` | Middle fidelity; failures mostly came from translated or dropped literal constraints. |

Built-in prompt sources:

- `hard_cases`: built-in literal and format preservation prompts covering verbatim repeat, bullet templates, exact markers, section separators, case/count constraints, symbols, JSON keys, and URLs
- [MT-Bench](https://raw.githubusercontent.com/lm-sys/FastChat/main/fastchat/llm_judge/data/mt_bench/question.jsonl)
- [IFEval](https://raw.githubusercontent.com/google-research/google-research/master/instruction_following_eval/data/input_data.jsonl)

The benchmark reports:

- per-judge pass rate with 95% Wilson confidence intervals
- panel consensus pass rate
- before-gate token reduction, showing how much the raw shortest candidate compressed before fidelity checks
- after-gate token reduction, showing accepted compression after literal and judge gates
- 95% bootstrap confidence intervals for mean token reduction
- pairwise judge agreement and Cohen's kappa
- per-dataset breakdowns

Example: rerun the benchmark on hard cases and public real-world cases

```bash
promptcrab-benchmark \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-reasoning-effort medium \
  --judge gemini_cli:gemini-3-flash-preview \
  --judge opencode_cli:minimax-coding-plan/MiniMax-M2.7-highspeed \
  --dataset hard_cases \
  --dataset mt_bench \
  --dataset ifeval \
  --cases-per-dataset 24 \
  --trials 2 \
  --tokenizer o200k_base
```

If you want to run the full datasets instead of a stratified sample:

```bash
promptcrab-benchmark \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-reasoning-effort medium \
  --judge gemini_cli:gemini-3-flash-preview \
  --judge opencode_cli:minimax-coding-plan/MiniMax-M2.7-highspeed \
  --dataset hard_cases \
  --dataset mt_bench \
  --dataset ifeval \
  --cases-per-dataset 0 \
  --tokenizer o200k_base
```

The built-in `hard_cases` suite is always evaluated in full when selected; `--cases-per-dataset` only limits sampled external datasets.

Recommended starting points:

- For highest fidelity and stability, use `codex_cli --model gpt-5.4`, optionally pin `--codex-reasoning-effort medium|high|xhigh`, and pick a different judge backend such as `gemini_cli` or `opencode_cli`.
- For strongest prompt compression, compare `opencode_cli --model minimax-coding-plan/MiniMax-M2.7-highspeed` with `codex_cli --model gpt-5.4` as judge.
- Use `gemini_cli --model gemini-3-flash-preview` as a rewrite backend only if you want to compare it explicitly; current literal-fidelity performance is weaker than `gpt-5.4` in the directional snapshot above.

If you omit `--judge-backend`, promptcrab skips judge-based verification and only applies literal checks. This is faster, but less safe.

Example: safer default rewrite

```bash
promptcrab \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-reasoning-effort medium \
  --judge-backend gemini_cli \
  --judge-model gemini-3-flash-preview \
  --prompt-file ./prompt.txt
```

Example: stronger compression with an external judge

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --judge-backend codex_cli \
  --judge-model gpt-5.4 \
  --judge-codex-reasoning-effort medium \
  --prompt-file ./prompt.txt
```

For `codex_cli`, promptcrab can override reasoning effort with `--codex-reasoning-effort` and `--judge-codex-reasoning-effort`. If you omit those flags, Codex falls back to your local CLI configuration such as `~/.codex/config.toml`.

## Output Modes

- Default output: prints the selected best prompt
- `--show-all`: prints all candidates, checks, and verifier results
- `--json-output`: prints a JSON object for automation
- `--write-best-to`: saves the selected prompt to a file

## Notes

- If no candidate passes the fidelity gates, `promptcrab` returns the original prompt unchanged.
- In normal mode, promptcrab generates a `canonical` candidate first, then generates translated candidates from it. Translated candidates do not silently switch back to the original prompt as their source.
- The `wenyan` candidate is strict Wenyan; it is not allowed to return modern Chinese under the `wenyan` label.
- If you set `--judge-backend`, promptcrab generates translated language candidates in parallel, skips judge calls for literal-invalid candidates, and judges the cheapest surviving candidate first before expanding to the rest.
- If you omit `--judge-backend`, promptcrab skips semantic verification and only uses literal checks.
- If you want a truly independent judge, set `--judge-backend` to a different backend than `--backend`.
- `promptcrab` does not set a generation output cap by default; if you need one for a specific backend or model, pass `--max-output-tokens`.
- `--max-output-tokens` is currently forwarded to `minimax` and `gemini`; `codex_cli` and `gemini_cli` do not expose a matching flag in this wrapper yet.
- `promptcrab` now defaults to shared local token counting with `--tokenizer o200k_base` for fast, deterministic counts without backend/API fallback.
- If you need the previous backend-native token counting path, pass `--tokenizer backend`.
- The selected best candidate is language-agnostic; whichever valid rewrite is smallest wins.

## Changelog

See [CHANGELOG.md](./CHANGELOG.md).
