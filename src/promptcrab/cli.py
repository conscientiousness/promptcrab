from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from dotenv import find_dotenv, load_dotenv

from promptcrab import __version__
from promptcrab.errors import PipelineError
from promptcrab.models import BackendName, PipelineConfig, PipelineResult
from promptcrab.pipeline import run_pipeline

CODEX_REASONING_EFFORT_CHOICES = ["low", "medium", "high", "xhigh"]


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promptcrab",
        description=(
            "Generate zh / wenyan / en prompt rewrites, verify them, count "
            "tokens, and pick the best one."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--backend",
        required=True,
        choices=["minimax", "gemini", "gemini_cli", "codex_cli"],
    )
    parser.add_argument("--model", required=True, help="Model name for the selected backend.")
    parser.add_argument(
        "--judge-backend",
        choices=["minimax", "gemini", "gemini_cli", "codex_cli"],
        help=(
            "Optional backend used only for verification/judging. If omitted, promptcrab "
            "skips judge-based verification."
        ),
    )
    parser.add_argument(
        "--judge-model",
        help="Model used only for verification/judging.",
    )
    parser.add_argument("--prompt", help="Original prompt text.")
    parser.add_argument(
        "--prompt-file",
        help="Path to a UTF-8 file containing the original prompt.",
    )
    parser.add_argument(
        "--env-file",
        help=(
            "Optional path to a .env file. If omitted, promptcrab searches for .env "
            "from the current working directory upward."
        ),
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Print all candidates and their checks.",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    parser.add_argument(
        "--write-best-to",
        help="Optional path to write the best optimized prompt.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per-call timeout in seconds.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        help=(
            "Optional backend-specific output token cap. If omitted, promptcrab "
            "leaves output length unset and uses provider defaults."
        ),
    )
    parser.add_argument(
        "--minimax-api-key",
        help="Overrides MINIMAX_API_KEY / OPENAI_API_KEY for MiniMax.",
    )
    parser.add_argument(
        "--minimax-base-url",
        default="https://api.minimax.io/v1",
    )
    parser.add_argument("--gemini-api-key", help="Overrides GEMINI_API_KEY for Gemini.")
    parser.add_argument("--gemini-executable", default="gemini")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument(
        "--codex-reasoning-effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        help="Optional Codex reasoning effort override for the rewrite backend.",
    )
    parser.add_argument(
        "--judge-codex-reasoning-effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        help="Optional Codex reasoning effort override for the judge backend.",
    )
    return parser


def read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if prompt_file:
        return Path(prompt_file).read_text(encoding="utf-8")
    if prompt:
        return prompt
    data = sys.stdin.read()
    if data.strip():
        return data
    raise PipelineError("Provide --prompt, --prompt-file, or pipe text via stdin.")


def build_config(args: argparse.Namespace) -> PipelineConfig:
    if args.max_output_tokens is not None and args.max_output_tokens <= 0:
        raise PipelineError("--max-output-tokens must be a positive integer.")
    if args.judge_model and not args.judge_backend:
        raise PipelineError("--judge-model requires --judge-backend.")
    return PipelineConfig(
        backend=cast(BackendName, args.backend),
        model=args.model,
        prompt=read_prompt(args.prompt, args.prompt_file).strip(),
        judge_backend=cast(BackendName | None, args.judge_backend),
        judge_model=args.judge_model,
        show_all=args.show_all,
        json_output=args.json_output,
        write_best_to=Path(args.write_best_to) if args.write_best_to else None,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
        minimax_api_key=args.minimax_api_key,
        minimax_base_url=args.minimax_base_url,
        gemini_api_key=args.gemini_api_key,
        gemini_executable=args.gemini_executable,
        codex_executable=args.codex_executable,
        codex_reasoning_effort=args.codex_reasoning_effort,
        judge_codex_reasoning_effort=args.judge_codex_reasoning_effort,
    )


def load_environment(env_file: str | None) -> None:
    loaded_paths: set[Path] = set()

    if env_file:
        explicit_path = Path(env_file).expanduser()
        if not explicit_path.is_file():
            raise PipelineError(f"Could not find env file: {explicit_path}")
        load_dotenv(dotenv_path=explicit_path, override=False)
        loaded_paths.add(explicit_path.resolve())

    discovered_path = find_dotenv(usecwd=True)
    if discovered_path:
        dotenv_path = Path(discovered_path).resolve()
        if dotenv_path not in loaded_paths:
            load_dotenv(dotenv_path=dotenv_path, override=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)

    try:
        load_environment(args.env_file)
        config = build_config(args)
        result = run_pipeline(config)
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if config.write_best_to:
        config.write_best_to.write_text(result.best_prompt, encoding="utf-8")

    if config.json_output:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_human_result(result, show_all=config.show_all)
    return 0


def print_human_result(result: PipelineResult, *, show_all: bool) -> None:
    print(f"Backend: {result.backend} | Model: {result.model}")
    if result.judge_backend and result.judge_model:
        print(f"Judge: {result.judge_backend} | Model: {result.judge_model}")
    else:
        print("Judge: disabled")
    if result.original_token_count is not None:
        print(
            "Original token count: "
            f"{result.original_token_count} ({result.original_token_count_source})"
        )
    else:
        print("Original token count: unavailable")
    print()

    if show_all:
        for candidate in result.candidates:
            print(
                f"[{candidate.lang}] tokens={candidate.token_count} "
                f"source={candidate.token_count_source} valid={candidate.valid}"
            )
            if not candidate.literal_check.get("ok", False):
                missing_literals = json.dumps(
                    candidate.literal_check.get("missing", {}),
                    ensure_ascii=False,
                )
                print(f"  missing_literals_python={missing_literals}")
            verifier_view = {
                key: value for key, value in candidate.verifier.items() if key != "_meta"
            }
            print(f"  verifier={json.dumps(verifier_view, ensure_ascii=False)}")
            print("  text:")
            print(indent_block(candidate.text, prefix="    "))
            print()

    if result.fallback_to_original:
        print("No candidate passed fidelity gates. Returning ORIGINAL prompt unchanged.")
        if result.fallback_reasons:
            print("Reasons:")
            for reason in result.fallback_reasons:
                print(f"- {reason}")
        print()
    else:
        best_token_source = next(
            candidate.token_count_source
            for candidate in result.candidates
            if candidate.lang == result.best_lang
        )
        best_summary = (
            f"Best candidate: {result.best_lang} | "
            f"tokens={result.best_token_count} "
            f"({best_token_source})"
        )
        print(best_summary)
        if result.original_token_count is not None and result.best_token_count is not None:
            delta = result.original_token_count - result.best_token_count
            print(f"Estimated saving vs original: {delta} tokens")
        print()

    print(result.best_prompt)


def indent_block(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())
