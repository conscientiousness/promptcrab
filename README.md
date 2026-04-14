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

`promptcrab` is a CLI for rewriting prompts for downstream LLMs with lower token cost and strict fidelity checks.

Instead of simply shortening text, it generates multiple rewrite candidates, verifies that they preserve task meaning and ordering, checks protected literals such as URLs, IDs, keys, and numbers, and then returns the safest compact version.

Requires Python 3.12 or newer.

## What It Does

- Rewrites a prompt into compact `zh`, `wenyan`, and `en` candidates
- Optionally verifies each candidate with a dedicated judge backend
- Checks whether important literals were dropped
- Estimates token counts
- Picks the best valid candidate, or falls back to the original prompt

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

Rewrite a prompt with MiniMax:

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7 \
  --prompt "Summarize this API design and keep every field name unchanged."
```

Rewrite a prompt from a file:

```bash
promptcrab \
  --backend gemini \
  --model gemini-3.1-pro-preview \
  --prompt-file ./prompt.txt
```

Use a fixed judge backend instead of self-verification:

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7-highspeed \
  --judge-backend codex_cli \
  --judge-model gpt-5.4 \
  --prompt-file ./prompt.txt
```

Rewrite a prompt with the local Gemini CLI:

```bash
promptcrab \
  --backend gemini_cli \
  --model gemini-2.5-flash \
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
  --backend minimax \
  --model MiniMax-M2.7 \
  --prompt-file ./prompt.txt \
  --show-all
```

Return machine-readable JSON:

```bash
promptcrab \
  --backend gemini \
  --model gemini-3.1-pro-preview \
  --prompt-file ./prompt.txt \
  --json-output
```

Write the best prompt to a file:

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7 \
  --prompt-file ./prompt.txt \
  --write-best-to ./optimized.txt
```

Optionally cap generation output if a specific provider/model needs it:

```bash
promptcrab \
  --backend gemini \
  --model gemini-3.1-pro-preview \
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

Current internal benchmark snapshot is still small and should be treated as directional, not final.
The figures below are based on 2 prompt samples, scored with two external judges per rewrite backend and re-counted with a shared tokenizer.

| Rewrite Backend | Suggested Use | Cross-Judge Pass Rate | Consensus Pass Rate | Avg Best Token Reduction |
|---|---|---:|---:|---:|
| `codex_cli` + `gpt-5.4` | safest general-purpose rewrite | `100.0%` | `100.0%` | `11.1%` |
| `minimax` + `MiniMax-M2.7-highspeed` | strongest compression with external judging | `75.0%` | `50.0%` | `18.7%` |
| `gemini_cli` + `gemini-3.1-pro-preview` | experimental; lower cross-judge agreement so far | `50.0%` | `0.0%` | `12.1%` |

Recommended starting points:

- For highest fidelity and stability, use `codex_cli --model gpt-5.4`, optionally pin `--codex-reasoning-effort medium|high|xhigh`, and pick a different judge backend such as `gemini_cli` or `minimax`.
- For strongest prompt compression, use `minimax --model MiniMax-M2.7-highspeed` with `codex_cli --model gpt-5.4` as judge.
- Use `gemini_cli --model gemini-3.1-pro-preview` as a rewrite backend only if you want to compare it explicitly; current cross-judge agreement is weaker.

If you omit `--judge-backend`, promptcrab skips judge-based verification and only applies literal checks. This is faster, but less safe.

Example: safer default rewrite

```bash
promptcrab \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-reasoning-effort medium \
  --judge-backend gemini_cli \
  --judge-model gemini-3.1-pro-preview \
  --prompt-file ./prompt.txt
```

Example: stronger compression with an external judge

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7-highspeed \
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
- If you set `--judge-backend`, promptcrab runs an extra verification pass before accepting a candidate.
- If you omit `--judge-backend`, promptcrab skips semantic verification and only uses literal checks.
- If you want a truly independent judge, set `--judge-backend` to a different backend than `--backend`.
- `promptcrab` does not set a generation output cap by default; if you need one for a specific backend or model, pass `--max-output-tokens`.
- `--max-output-tokens` is currently forwarded to `minimax` and `gemini`; `codex_cli` and `gemini_cli` do not expose a matching flag in this wrapper yet.
- Token counting depends on backend support and available credentials.
- The selected best candidate is language-agnostic; whichever valid rewrite is smallest wins.

## Changelog

See [CHANGELOG.md](./CHANGELOG.md).
