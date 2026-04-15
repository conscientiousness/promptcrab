from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, cast

from promptcrab.backends import build_backend
from promptcrab.cli import CODEX_REASONING_EFFORT_CHOICES, load_environment
from promptcrab.errors import PipelineError
from promptcrab.models import BackendName, Candidate, PipelineConfig
from promptcrab.pipeline import (
    candidate_sort_key,
    count_original_tokens,
    generate_candidate,
    is_candidate_valid,
    judge_candidate,
)
from promptcrab.preflight import classify_prompt

DEFAULT_DATASETS = ("hard_cases", "mt_bench", "ifeval")
DEFAULT_CASES_PER_DATASET = 24
DEFAULT_BOOTSTRAP_SAMPLES = 1000
DATASET_FETCH_TIMEOUT = 60


@dataclass(frozen=True, slots=True)
class BackendSpec:
    backend: BackendName
    model: str
    codex_reasoning_effort: str | None = None

    @property
    def label(self) -> str:
        return f"{self.backend} + {self.model}"


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    dataset: str
    prompt: str
    source_url: str
    title: str
    category: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    name: str
    url: str
    description: str
    parser: Callable[[str, str], list[BenchmarkCase]]


@dataclass(slots=True)
class BenchmarkConfig:
    rewrite: BackendSpec
    judges: list[BackendSpec]
    datasets: list[str]
    cases_per_dataset: int | None
    trials: int
    seed: int
    tokenizer: str
    cache_dir: Path
    refresh_datasets: bool
    timeout: int
    max_output_tokens: int | None
    env_file: str | None
    minimax_api_key: str | None
    minimax_base_url: str
    gemini_api_key: str | None
    gemini_executable: str
    codex_executable: str
    opencode_executable: str
    codex_reasoning_effort: str | None
    judge_codex_reasoning_effort: str | None
    bootstrap_samples: int


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promptcrab-benchmark",
        description=(
            "Run reproducible promptcrab benchmarks against built-in hard cases "
            "and public web datasets with multiple judges and shared token counting."
        ),
    )
    parser.add_argument(
        "--backend",
        required=True,
        choices=["minimax", "gemini", "gemini_cli", "codex_cli", "opencode_cli"],
        help="Rewrite backend under test.",
    )
    parser.add_argument("--model", required=True, help="Rewrite model under test.")
    parser.add_argument(
        "--judge",
        action="append",
        default=[],
        help=(
            "Judge backend spec in backend:model form. Repeat for multi-judge panels, "
            "for example --judge codex_cli:gpt-5.4 --judge gemini_cli:gemini-2.5-pro."
        ),
    )
    parser.add_argument(
        "--dataset",
        action="append",
        choices=sorted(DATASET_DEFINITIONS),
        default=None,
        help="Benchmark dataset to use. Repeat to combine multiple datasets.",
    )
    parser.add_argument(
        "--cases-per-dataset",
        type=int,
        default=DEFAULT_CASES_PER_DATASET,
        help=(
            "Maximum sampled cases per dataset. Sampling is category-aware when the "
            "dataset exposes categories. Use 0 to evaluate the full dataset."
        ),
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="How many times to run each sampled case.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Random seed used for sampling and bootstrap confidence intervals.",
    )
    parser.add_argument(
        "--tokenizer",
        default="o200k_base",
        help=(
            "Shared tokenizer used to re-count every prompt and candidate. Accepts a "
            "tiktoken encoding name or model name."
        ),
    )
    parser.add_argument(
        "--cache-dir",
        default=".promptcrab-benchmark-cache",
        help="Directory used to cache downloaded public datasets.",
    )
    parser.add_argument(
        "--refresh-datasets",
        action="store_true",
        help="Force re-download of public dataset sources instead of using cache.",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Emit machine-readable JSON instead of the human summary.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per model call timeout in seconds.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        help="Optional rewrite generation cap for supported backends.",
    )
    parser.add_argument("--env-file", help="Optional path to a .env file.")
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
    parser.add_argument("--opencode-executable", default="opencode")
    parser.add_argument(
        "--codex-reasoning-effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        help="Optional Codex reasoning effort override for the rewrite backend.",
    )
    parser.add_argument(
        "--judge-codex-reasoning-effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        help="Optional Codex reasoning effort override for Codex-based judges.",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=DEFAULT_BOOTSTRAP_SAMPLES,
        help="Bootstrap resamples used for mean token-reduction confidence intervals.",
    )
    return parser


def build_config(args: argparse.Namespace) -> BenchmarkConfig:
    if not args.judge:
        raise PipelineError("Provide at least one --judge backend:model pair.")
    if args.max_output_tokens is not None and args.max_output_tokens <= 0:
        raise PipelineError("--max-output-tokens must be a positive integer.")
    if args.cases_per_dataset < 0:
        raise PipelineError("--cases-per-dataset must be >= 0.")
    if args.trials <= 0:
        raise PipelineError("--trials must be a positive integer.")
    if args.bootstrap_samples <= 0:
        raise PipelineError("--bootstrap-samples must be a positive integer.")
    datasets = [str(name) for name in dict.fromkeys(args.dataset or DEFAULT_DATASETS)]
    judges = [parse_backend_spec(value, label="judge") for value in args.judge]
    return BenchmarkConfig(
        rewrite=BackendSpec(
            backend=cast(BackendName, args.backend),
            model=args.model,
            codex_reasoning_effort=args.codex_reasoning_effort,
        ),
        judges=judges,
        datasets=datasets,
        cases_per_dataset=args.cases_per_dataset or None,
        trials=args.trials,
        seed=args.seed,
        tokenizer=args.tokenizer,
        cache_dir=Path(args.cache_dir),
        refresh_datasets=args.refresh_datasets,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
        env_file=args.env_file,
        minimax_api_key=args.minimax_api_key,
        minimax_base_url=args.minimax_base_url,
        gemini_api_key=args.gemini_api_key,
        gemini_executable=args.gemini_executable,
        codex_executable=args.codex_executable,
        opencode_executable=args.opencode_executable,
        codex_reasoning_effort=args.codex_reasoning_effort,
        judge_codex_reasoning_effort=args.judge_codex_reasoning_effort,
        bootstrap_samples=args.bootstrap_samples,
    )


def parse_backend_spec(value: str, *, label: str) -> BackendSpec:
    backend, separator, model = value.partition(":")
    if separator == "" or not backend or not model:
        raise PipelineError(
            f"Invalid {label} spec {value!r}. Expected backend:model, "
            "for example codex_cli:gpt-5.4."
        )
    if backend not in {"minimax", "gemini", "gemini_cli", "codex_cli", "opencode_cli"}:
        raise PipelineError(f"Unknown backend in {label} spec: {backend}")
    return BackendSpec(
        backend=cast(BackendName, backend),
        model=model,
    )


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)

    try:
        load_environment(args.env_file)
        config = build_config(args)
        result = run_benchmark(config)
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human_summary(result)
    return 0


def run_benchmark(config: BenchmarkConfig) -> dict[str, Any]:
    token_counter = build_shared_token_counter(config.tokenizer)
    dataset_payload = load_public_cases(config)
    dataset_summaries = [
        {key: value for key, value in item.items() if key != "cases"}
        for item in dataset_payload
    ]
    rewrite_backend = build_runtime_backend(config, config.rewrite, is_judge=False)
    judge_backends = {
        judge.label: build_runtime_backend(config, judge, is_judge=True)
        for judge in config.judges
    }

    case_results: list[dict[str, Any]] = []
    for dataset_info in dataset_payload:
        for case in dataset_info["cases"]:
            for trial in range(config.trials):
                case_results.append(
                    run_case_once(
                        case=case,
                        trial=trial + 1,
                        rewrite_backend=rewrite_backend,
                        judge_backends=judge_backends,
                        token_counter=token_counter,
                        timeout=config.timeout,
                        max_output_tokens=config.max_output_tokens,
                    )
                )

    summary = summarize_benchmark(
        case_results,
        judge_labels=[judge.label for judge in config.judges],
        bootstrap_samples=config.bootstrap_samples,
        seed=config.seed,
    )
    return {
        "rewrite_backend": config.rewrite.label,
        "rewrite_backend_name": config.rewrite.backend,
        "rewrite_model": config.rewrite.model,
        "shared_tokenizer": config.tokenizer,
        "datasets": dataset_summaries,
        "trials_per_case": config.trials,
        "seed": config.seed,
        "judge_panel": [judge.label for judge in config.judges],
        "summary": summary,
        "results": case_results,
    }


def build_runtime_backend(config: BenchmarkConfig, spec: BackendSpec, *, is_judge: bool):
    pipeline_config = PipelineConfig(
        backend=spec.backend,
        model=spec.model,
        prompt="",
        timeout=config.timeout,
        max_output_tokens=config.max_output_tokens,
        minimax_api_key=config.minimax_api_key,
        minimax_base_url=config.minimax_base_url,
        gemini_api_key=config.gemini_api_key,
        gemini_executable=config.gemini_executable,
        codex_executable=config.codex_executable,
        opencode_executable=config.opencode_executable,
        codex_reasoning_effort=(
            config.judge_codex_reasoning_effort
            if is_judge and spec.backend == "codex_cli"
            else spec.codex_reasoning_effort
        ),
    )
    return build_backend(pipeline_config)


def build_shared_token_counter(tokenizer_name: str) -> Callable[[str], tuple[int, str]]:
    try:
        import tiktoken
    except Exception as exc:
        raise PipelineError("Shared benchmark token counting requires tiktoken.") from exc

    encoding = None
    source = f"tiktoken:{tokenizer_name}"
    try:
        encoding = tiktoken.encoding_for_model(tokenizer_name)
        source = f"tiktoken_model:{tokenizer_name}"
    except Exception:
        try:
            encoding = tiktoken.get_encoding(tokenizer_name)
            source = f"tiktoken_encoding:{tokenizer_name}"
        except Exception as exc:
            raise PipelineError(
                f"Unknown tokenizer or model for --tokenizer: {tokenizer_name}"
            ) from exc

    def _count(text: str) -> tuple[int, str]:
        return len(encoding.encode(text)), source

    return _count


def load_public_cases(config: BenchmarkConfig) -> list[dict[str, Any]]:
    dataset_payload: list[dict[str, Any]] = []
    for offset, dataset_name in enumerate(config.datasets):
        definition = DATASET_DEFINITIONS[dataset_name]
        if definition.url.startswith("builtin:"):
            raw_text = ""
        else:
            raw_text = fetch_cached_url(
                url=definition.url,
                cache_path=config.cache_dir / f"{dataset_name}.jsonl",
                refresh=config.refresh_datasets,
            )
        cases = definition.parser(raw_text, definition.url)
        sampled = (
            cases
            if definition.url.startswith("builtin:")
            else sample_cases(
                cases,
                max_cases=config.cases_per_dataset,
                seed=config.seed + offset,
            )
        )
        dataset_payload.append(
            {
                "name": definition.name,
                "description": definition.description,
                "source_url": definition.url,
                "available_case_count": len(cases),
                "sampled_case_count": len(sampled),
                "cases": sampled,
            }
        )
    return dataset_payload


def fetch_cached_url(url: str, cache_path: Path, *, refresh: bool) -> str:
    if cache_path.is_file() and not refresh:
        return cache_path.read_text(encoding="utf-8")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "promptcrab-benchmark/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=DATASET_FETCH_TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        if cache_path.is_file():
            return cache_path.read_text(encoding="utf-8")
        raise PipelineError(f"Failed to fetch dataset from {url}: {exc}") from exc

    cache_path.write_text(body, encoding="utf-8")
    return body


def parse_mt_bench_cases(raw_text: str, source_url: str) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for line in raw_text.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        question_id = payload["question_id"]
        category = payload.get("category")
        for turn_index, prompt in enumerate(payload.get("turns", []), start=1):
            cases.append(
                BenchmarkCase(
                    case_id=f"mt_bench:{question_id}:{turn_index}",
                    dataset="mt_bench",
                    prompt=prompt.strip(),
                    source_url=source_url,
                    title=f"MT-Bench question {question_id} turn {turn_index}",
                    category=category,
                    metadata={
                        "question_id": question_id,
                        "turn_index": turn_index,
                    },
                )
            )
    return cases


def parse_ifeval_cases(raw_text: str, source_url: str) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for line in raw_text.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        instruction_ids = payload.get("instruction_id_list") or []
        category = derive_ifeval_category(instruction_ids)
        cases.append(
            BenchmarkCase(
                case_id=f"ifeval:{payload['key']}",
                dataset="ifeval",
                prompt=payload["prompt"].strip(),
                source_url=source_url,
                title=f"IFEval prompt {payload['key']}",
                category=category,
                metadata={
                    "instruction_id_list": instruction_ids,
                    "kwargs": payload.get("kwargs", []),
                },
            )
        )
    return cases


def parse_hard_case_cases(raw_text: str, source_url: str) -> list[BenchmarkCase]:
    del raw_text
    prompts = [
        (
            "hard_cases:verbatim-repeat",
            "verbatim_repeat",
            "Repeat exactly this question without changing any words, then answer it: "
            "What is the name of the actor who played Gandalf in Lord of the Rings?",
        ),
        (
            "hard_cases:format-bullets",
            "format_template",
            "I need a list of the top 10 attorneys in the US. Your list should be in "
            "the format of 10 bullet points, following the format below:\n\n"
            "* Bullet 1\n* Bullet 2\n* ...",
        ),
        (
            "hard_cases:literal-markers",
            "literal_marker",
            "Write a rap about a new smartphone. At the end of your response add a "
            "postscript starting with P.P.S The response must contain at least 6 "
            "placeholders represented by square brackets.",
        ),
        (
            "hard_cases:separator-case-count",
            "separator_case_count",
            "Explain the difference between a city and a village in a rap style to a kid. "
            "The words with all capital letters should appear at least 10 times. Put the "
            "response into at least 5 sections, separated using 3 asterisks ***.",
        ),
        (
            "hard_cases:symbol-json-url",
            "symbol_structured_data",
            "Given x+y = 4z and x*y = 4z^2, express x-y in z. Return JSON with keys "
            '"answer" and "derivation", and keep https://example.com/a?x=1&y=two unchanged.',
        ),
    ]
    return [
        BenchmarkCase(
            case_id=case_id,
            dataset="hard_cases",
            prompt=prompt,
            source_url=source_url,
            title=f"Hard case: {category.replace('_', ' ')}",
            category=category,
            metadata={"suite": "literal_format_hard_cases"},
        )
        for case_id, category, prompt in prompts
    ]


def derive_ifeval_category(instruction_ids: list[str]) -> str | None:
    if not instruction_ids:
        return None
    first = instruction_ids[0]
    for separator in (":", ","):
        if separator in first:
            return first.split(separator, 1)[0]
    return first


def sample_cases(
    cases: list[BenchmarkCase],
    *,
    max_cases: int | None,
    seed: int,
) -> list[BenchmarkCase]:
    if max_cases is None or max_cases >= len(cases):
        return list(cases)

    rng = random.Random(seed)
    buckets: dict[str, list[BenchmarkCase]] = defaultdict(list)
    for case in cases:
        key = case.category or "_default"
        buckets[key].append(case)

    if len(buckets) == 1:
        sampled = rng.sample(cases, max_cases)
        sampled.sort(key=lambda case: case.case_id)
        return sampled

    for bucket in buckets.values():
        rng.shuffle(bucket)
    bucket_names = sorted(buckets)

    sampled: list[BenchmarkCase] = []
    while len(sampled) < max_cases and bucket_names:
        next_round: list[str] = []
        for bucket_name in bucket_names:
            bucket = buckets[bucket_name]
            if not bucket:
                continue
            sampled.append(bucket.pop())
            if bucket:
                next_round.append(bucket_name)
            if len(sampled) == max_cases:
                break
        bucket_names = next_round
    sampled.sort(key=lambda case: case.case_id)
    return sampled


def run_case_once(
    *,
    case: BenchmarkCase,
    trial: int,
    rewrite_backend,
    judge_backends: dict[str, Any],
    token_counter: Callable[[str], tuple[int, str]],
    timeout: int,
    max_output_tokens: int | None,
) -> dict[str, Any]:
    prompt_risk = classify_prompt(case.prompt)
    original_token_count, original_token_source = count_original_tokens(
        case.prompt,
        token_counter=token_counter,
    )
    candidates = [
        generate_candidate(
            backend=rewrite_backend,
            original_prompt=case.prompt,
            lang=lang,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
            token_counter=token_counter,
            prompt_risk=prompt_risk,
        )
        for lang in prompt_risk.languages
    ]

    candidate_judgments: dict[str, dict[str, dict[str, Any]]] = {}
    judge_case_results: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        candidate_judgments[candidate.lang] = {}
        for judge_label, judge_backend_instance in judge_backends.items():
            verifier = judge_candidate(
                judge_backend=judge_backend_instance,
                original_prompt=case.prompt,
                candidate_text=candidate.text,
                timeout=timeout,
            )
            candidate_judgments[candidate.lang][judge_label] = {
                "valid": is_candidate_valid(candidate, verifier=verifier),
                "ambiguity_count": ambiguity_count(verifier),
                "verifier": sanitize_verifier(verifier),
            }

    for judge_label in judge_backends:
        best_candidate = pick_best_candidate_for_judge(
            candidates,
            candidate_judgments=candidate_judgments,
            judge_label=judge_label,
        )
        judge_case_results[judge_label] = serialize_case_outcome(
            best_candidate,
            original_token_count=original_token_count,
        )

    consensus_best = pick_consensus_best_candidate(
        candidates,
        candidate_judgments=candidate_judgments,
        judge_labels=list(judge_backends),
    )
    before_gate_best = pick_before_gate_best_candidate(candidates)
    serialized_candidates = [
        serialize_benchmark_candidate(candidate, candidate_judgments[candidate.lang])
        for candidate in candidates
    ]
    consensus = serialize_case_outcome(
        consensus_best,
        original_token_count=original_token_count,
    )
    consensus["pass"] = consensus_best is not None

    return {
        "case_id": case.case_id,
        "dataset": case.dataset,
        "category": case.category,
        "source_url": case.source_url,
        "title": case.title,
        "trial": trial,
        "prompt": case.prompt,
        "metadata": case.metadata,
        "prompt_risk": prompt_risk.to_dict(),
        "original_token_count": original_token_count,
        "original_token_count_source": original_token_source,
        "candidates": serialized_candidates,
        "before_gate": serialize_token_outcome(
            before_gate_best,
            original_token_count=original_token_count,
        ),
        "judges": judge_case_results,
        "consensus": consensus,
    }


def sanitize_verifier(verifier: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in verifier.items() if key != "_meta"}


def ambiguity_count(verifier: dict[str, Any]) -> int:
    value = verifier.get("ambiguities", [])
    return len(value) if isinstance(value, list) else 0


def pick_best_candidate_for_judge(
    candidates: list[Candidate],
    *,
    candidate_judgments: dict[str, dict[str, dict[str, Any]]],
    judge_label: str,
) -> Candidate | None:
    valid = [
        candidate
        for candidate in candidates
        if candidate_judgments[candidate.lang][judge_label]["valid"]
    ]
    valid.sort(
        key=lambda candidate: candidate_sort_key(
            candidate,
            ambiguity_count=candidate_judgments[candidate.lang][judge_label]["ambiguity_count"],
        )
    )
    return valid[0] if valid else None


def pick_consensus_best_candidate(
    candidates: list[Candidate],
    *,
    candidate_judgments: dict[str, dict[str, dict[str, Any]]],
    judge_labels: list[str],
) -> Candidate | None:
    valid = [
        candidate
        for candidate in candidates
        if all(candidate_judgments[candidate.lang][label]["valid"] for label in judge_labels)
    ]
    valid.sort(
        key=lambda candidate: candidate_sort_key(
            candidate,
            ambiguity_count=max(
                candidate_judgments[candidate.lang][label]["ambiguity_count"]
                for label in judge_labels
            ),
        )
    )
    return valid[0] if valid else None


def pick_before_gate_best_candidate(candidates: list[Candidate]) -> Candidate | None:
    counted = [candidate for candidate in candidates if candidate.token_count is not None]
    counted.sort(key=candidate_sort_key)
    return counted[0] if counted else None


def serialize_benchmark_candidate(
    candidate: Candidate,
    judgments: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "lang": candidate.lang,
        "text": candidate.text,
        "token_count": candidate.token_count,
        "token_count_source": candidate.token_count_source,
        "literal_check": candidate.literal_check,
        "judges": judgments,
    }


def serialize_case_outcome(
    candidate: Candidate | None,
    *,
    original_token_count: int | None,
) -> dict[str, Any]:
    if candidate is None:
        return {
            "pass": False,
            "best_lang": None,
            "best_token_count": None,
            "token_reduction_ratio": None,
        }
    payload = serialize_token_outcome(candidate, original_token_count=original_token_count)
    payload["pass"] = True
    return payload


def serialize_token_outcome(
    candidate: Candidate | None,
    *,
    original_token_count: int | None,
) -> dict[str, Any]:
    if candidate is None:
        return {
            "best_lang": None,
            "best_token_count": None,
            "token_reduction_ratio": None,
        }
    return {
        "best_lang": candidate.lang,
        "best_token_count": candidate.token_count,
        "token_reduction_ratio": compute_token_reduction_ratio(
            original_token_count=original_token_count,
            candidate_token_count=candidate.token_count,
        ),
    }


def compute_token_reduction_ratio(
    *,
    original_token_count: int | None,
    candidate_token_count: int | None,
) -> float | None:
    if (
        original_token_count is None
        or candidate_token_count is None
        or original_token_count <= 0
    ):
        return None
    return (original_token_count - candidate_token_count) / original_token_count


def summarize_benchmark(
    results: list[dict[str, Any]],
    *,
    judge_labels: list[str],
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    return {
        "panel_runs": len(results),
        "judge_pass_rates": {
            label: summarize_binary_rate(
                sum(1 for result in results if result["judges"][label]["pass"]),
                len(results),
            )
            for label in judge_labels
        },
        "consensus_pass_rate": summarize_binary_rate(
            sum(1 for result in results if result["consensus"]["pass"]),
            len(results),
        ),
        "judge_agreement": summarize_judge_agreement(results, judge_labels),
        "before_gate_token_reduction": summarize_distribution(
            [
                result["before_gate"]["token_reduction_ratio"]
                for result in results
                if result["before_gate"]["token_reduction_ratio"] is not None
            ],
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ),
        "after_gate_token_reduction": summarize_distribution(
            [
                result["consensus"]["token_reduction_ratio"]
                for result in results
                if result["consensus"]["token_reduction_ratio"] is not None
            ],
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ),
        "consensus_token_reduction": summarize_distribution(
            [
                result["consensus"]["token_reduction_ratio"]
                for result in results
                if result["consensus"]["token_reduction_ratio"] is not None
            ],
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ),
        "by_dataset": {
            dataset: summarize_dataset_slice(
                [result for result in results if result["dataset"] == dataset],
                judge_labels=judge_labels,
                bootstrap_samples=bootstrap_samples,
                seed=seed,
            )
            for dataset in sorted({result["dataset"] for result in results})
        },
    }


def summarize_dataset_slice(
    results: list[dict[str, Any]],
    *,
    judge_labels: list[str],
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    return {
        "panel_runs": len(results),
        "consensus_pass_rate": summarize_binary_rate(
            sum(1 for result in results if result["consensus"]["pass"]),
            len(results),
        ),
        "before_gate_token_reduction": summarize_distribution(
            [
                result["before_gate"]["token_reduction_ratio"]
                for result in results
                if result["before_gate"]["token_reduction_ratio"] is not None
            ],
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ),
        "after_gate_token_reduction": summarize_distribution(
            [
                result["consensus"]["token_reduction_ratio"]
                for result in results
                if result["consensus"]["token_reduction_ratio"] is not None
            ],
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ),
        "consensus_token_reduction": summarize_distribution(
            [
                result["consensus"]["token_reduction_ratio"]
                for result in results
                if result["consensus"]["token_reduction_ratio"] is not None
            ],
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ),
        "judge_pass_rates": {
            label: summarize_binary_rate(
                sum(1 for result in results if result["judges"][label]["pass"]),
                len(results),
            )
            for label in judge_labels
        },
    }


def summarize_binary_rate(successes: int, total: int) -> dict[str, Any]:
    rate = successes / total if total else None
    ci_low, ci_high = wilson_interval(successes, total)
    return {
        "successes": successes,
        "total": total,
        "rate": rate,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
    }


def summarize_distribution(
    values: list[float],
    *,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "stdev": None,
            "ci95_low": None,
            "ci95_high": None,
        }

    stdev = statistics.stdev(values) if len(values) >= 2 else 0.0
    ci_low, ci_high = bootstrap_mean_ci(
        values,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": stdev,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
    }


def summarize_judge_agreement(
    results: list[dict[str, Any]],
    judge_labels: list[str],
) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for left, right in combinations(judge_labels, 2):
        pairs = [
            (
                bool(result["judges"][left]["pass"]),
                bool(result["judges"][right]["pass"]),
            )
            for result in results
        ]
        agreement = (
            sum(1 for left_pass, right_pass in pairs if left_pass == right_pass) / len(pairs)
            if pairs
            else None
        )
        comparisons.append(
            {
                "left": left,
                "right": right,
                "agreement_rate": agreement,
                "cohen_kappa": cohen_kappa(pairs),
            }
        )
    return comparisons


def wilson_interval(
    successes: int,
    total: int,
    z: float = 1.96,
) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    p = successes / total
    denominator = 1 + (z**2 / total)
    center = (p + z**2 / (2 * total)) / denominator
    margin = (z / denominator) * math.sqrt((p * (1 - p) / total) + (z**2 / (4 * total**2)))
    return max(0.0, center - margin), min(1.0, center + margin)


def bootstrap_mean_ci(
    values: list[float],
    *,
    bootstrap_samples: int,
    seed: int,
) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]

    rng = random.Random(seed)
    means = []
    for _ in range(bootstrap_samples):
        sample = [rng.choice(values) for _ in range(len(values))]
        means.append(statistics.fmean(sample))
    means.sort()
    low_index = int(0.025 * (len(means) - 1))
    high_index = int(0.975 * (len(means) - 1))
    return means[low_index], means[high_index]


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    if not pairs:
        return None
    total = len(pairs)
    observed = sum(1 for left, right in pairs if left == right) / total
    left_true = sum(1 for left, _ in pairs if left) / total
    right_true = sum(1 for _, right in pairs if right) / total
    expected = left_true * right_true + (1 - left_true) * (1 - right_true)
    if math.isclose(expected, 1.0):
        return 1.0
    return (observed - expected) / (1 - expected)


def print_human_summary(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print(f"Rewrite backend: {result['rewrite_backend']}")
    print(f"Shared tokenizer: {result['shared_tokenizer']}")
    print(f"Judge panel: {', '.join(result['judge_panel'])}")
    print(f"Panel runs: {summary['panel_runs']}")
    print()

    print("Datasets:")
    for dataset in result["datasets"]:
        print(
            f"- {dataset['name']}: sampled {dataset['sampled_case_count']} / "
            f"{dataset['available_case_count']} cases"
        )
        print(f"  source: {dataset['source_url']}")
    print()

    consensus = summary["consensus_pass_rate"]
    before_gate_reduction = summary["before_gate_token_reduction"]
    after_gate_reduction = summary["after_gate_token_reduction"]
    print(
        "Consensus pass rate: "
        f"{format_pct(consensus['rate'])} "
        f"(95% CI {format_pct(consensus['ci95_low'])} to {format_pct(consensus['ci95_high'])})"
    )
    print(
        "Before-gate token reduction: "
        f"mean {format_pct(before_gate_reduction['mean'])}, "
        f"median {format_pct(before_gate_reduction['median'])}, "
        f"stdev {format_pct(before_gate_reduction['stdev'])}"
    )
    print(
        "After-gate token reduction: "
        f"mean {format_pct(after_gate_reduction['mean'])}, "
        f"median {format_pct(after_gate_reduction['median'])}, "
        f"stdev {format_pct(after_gate_reduction['stdev'])}"
    )
    if after_gate_reduction["ci95_low"] is not None:
        print(
            "After-gate token reduction mean 95% CI: "
            f"{format_pct(after_gate_reduction['ci95_low'])} to "
            f"{format_pct(after_gate_reduction['ci95_high'])}"
        )
    print()

    print("Judge pass rates:")
    for label, payload in summary["judge_pass_rates"].items():
        print(
            f"- {label}: {format_pct(payload['rate'])} "
            f"(95% CI {format_pct(payload['ci95_low'])} to {format_pct(payload['ci95_high'])})"
        )
    if summary["judge_agreement"]:
        print()
        print("Judge agreement:")
        for payload in summary["judge_agreement"]:
            print(
                f"- {payload['left']} vs {payload['right']}: "
                f"agreement {format_pct(payload['agreement_rate'])}, "
                f"kappa {format_float(payload['cohen_kappa'])}"
            )
    print()

    print("By dataset:")
    for dataset, payload in summary["by_dataset"].items():
        print(
            f"- {dataset}: pass {format_pct(payload['consensus_pass_rate']['rate'])}, "
            f"before-gate mean {format_pct(payload['before_gate_token_reduction']['mean'])}, "
            f"after-gate mean {format_pct(payload['after_gate_token_reduction']['mean'])}"
        )


def format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


DATASET_DEFINITIONS: dict[str, DatasetDefinition] = {
    "hard_cases": DatasetDefinition(
        name="hard_cases",
        url="builtin:hard_cases",
        description="Built-in literal and format preservation hard-case prompts.",
        parser=parse_hard_case_cases,
    ),
    "mt_bench": DatasetDefinition(
        name="mt_bench",
        url=(
            "https://raw.githubusercontent.com/lm-sys/FastChat/main/"
            "fastchat/llm_judge/data/mt_bench/question.jsonl"
        ),
        description="LM-Sys MT-Bench public evaluation prompts.",
        parser=parse_mt_bench_cases,
    ),
    "ifeval": DatasetDefinition(
        name="ifeval",
        url=(
            "https://raw.githubusercontent.com/google-research/google-research/master/"
            "instruction_following_eval/data/input_data.jsonl"
        ),
        description="Google Instruction Following Eval public prompts.",
        parser=parse_ifeval_cases,
    ),
}
