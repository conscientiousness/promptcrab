from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import replace
from itertools import groupby
from typing import Any

from promptcrab.backends import build_backend
from promptcrab.constants import (
    CANONICAL_LANGUAGE,
    REWRITE_SYSTEM,
    VERIFIER_SCHEMA,
    VERIFIER_SYSTEM,
)
from promptcrab.errors import PipelineError
from promptcrab.literal_checks import literal_coverage
from promptcrab.models import Candidate, PipelineConfig, PipelineResult
from promptcrab.parsing import parse_json_response, strip_code_fences
from promptcrab.preflight import PromptRisk, classify_prompt
from promptcrab.prompts import build_rewrite_user_prompt, build_verifier_user_prompt

TOKEN_COUNT_TIMEOUT = 120
JUDGE_PARSE_RETRIES = 2
MAX_PARALLEL_WORKERS = 4
TokenCounter = Callable[[str], tuple[int, str]]

WENYAN_STRONG_MODERN_MARKERS = (
    "不是",
    "而是",
    "你必須",
    "你可以",
)
WENYAN_MODERN_MARKERS = (
    "必須",
    "可以",
    "例如",
    "以及",
    "進行",
    "使用",
    "找到",
    "才能",
    "以上",
    "不同",
    "影響",
    "搜尋",
    "網路",
)


def candidate_sort_key(
    candidate: Candidate,
    *,
    ambiguity_count: int | None = None,
) -> tuple[int, int, int]:
    return (
        candidate.token_count if candidate.token_count is not None else 10**9,
        candidate.ambiguity_count() if ambiguity_count is None else ambiguity_count,
        len(candidate.text),
    )


def choose_best(
    candidates: list[Candidate],
    original_prompt: str,
) -> tuple[str, Candidate | None, list[str]]:
    valid = [
        candidate
        for candidate in candidates
        if candidate.valid and candidate.token_count is not None
    ]
    valid.sort(key=candidate_sort_key)
    if valid:
        best = valid[0]
        return best.text, best, []

    reasons: list[str] = []
    for candidate in candidates:
        reason = f"{candidate.lang}: invalid"
        if candidate.literal_check and not candidate.literal_check.get("ok", False):
            reason += f"; missing literals={candidate.literal_check.get('missing', {})}"
        if candidate.verifier:
            reason += f"; faithful={candidate.verifier.get('faithful')}"
            if candidate.verifier.get("ambiguities"):
                reason += f"; ambiguities={candidate.verifier.get('ambiguities')}"
        if candidate.warnings:
            reason += f"; warnings={candidate.warnings}"
        reasons.append(reason)
    return original_prompt, None, reasons


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    backend = build_backend(config)
    judge_backend = None
    if config.judge_backend and config.judge_model:
        judge_backend = build_backend(
            replace(
                config,
                backend=config.judge_backend,
                model=config.judge_model,
                codex_reasoning_effort=config.judge_codex_reasoning_effort,
            )
        )
    token_counter = build_token_counter(config=config, backend=backend)
    prompt_risk = classify_prompt(config.prompt)

    candidates = generate_candidates(
        backend=backend,
        original_prompt=config.prompt,
        languages=prompt_risk.languages,
        prompt_risk=prompt_risk,
        timeout=config.timeout,
        max_output_tokens=config.max_output_tokens,
        token_counter=token_counter,
    )
    evaluate_candidates(
        candidates=candidates,
        judge_backend=judge_backend,
        original_prompt=config.prompt,
        timeout=config.timeout,
    )

    original_token_count, original_token_source = count_original_tokens(
        config.prompt,
        token_counter=token_counter,
    )

    best_text, best_candidate, fallback_reasons = choose_best(candidates, config.prompt)
    return PipelineResult(
        backend=backend.name,
        model=backend.model,
        judge_backend=judge_backend.name if judge_backend else None,
        judge_model=judge_backend.model if judge_backend else None,
        original_prompt=config.prompt,
        original_token_count=original_token_count,
        original_token_count_source=original_token_source,
        candidates=candidates,
        best_prompt=best_text,
        best_lang=best_candidate.lang if best_candidate else None,
        best_token_count=best_candidate.token_count if best_candidate else original_token_count,
        fallback_to_original=best_candidate is None,
        fallback_reasons=fallback_reasons,
        generated_at_unix=int(time.time()),
        prompt_risk=prompt_risk.to_dict(),
    )


def _evaluate_candidate(
    *,
    backend,
    judge_backend,
    original_prompt: str,
    lang: str,
    timeout: int,
    max_output_tokens: int | None,
    token_counter: TokenCounter | None = None,
    prompt_risk: PromptRisk | None = None,
) -> Candidate:
    candidate = generate_candidate(
        backend=backend,
        original_prompt=original_prompt,
        lang=lang,
        prompt_risk=prompt_risk,
        timeout=timeout,
        max_output_tokens=max_output_tokens,
        token_counter=token_counter,
    )

    if judge_backend is not None:
        verifier = judge_candidate(
            judge_backend=judge_backend,
            original_prompt=original_prompt,
            candidate_text=candidate.text,
            timeout=timeout,
        )
        candidate.verifier = verifier

    candidate.valid = is_candidate_valid(candidate)
    return candidate


def generate_candidates(
    *,
    backend,
    original_prompt: str,
    languages: tuple[str, ...],
    prompt_risk: PromptRisk,
    timeout: int,
    max_output_tokens: int | None,
    token_counter: TokenCounter | None = None,
    parallel: bool = True,
) -> list[Candidate]:
    if not languages:
        raise PipelineError("At least one rewrite language is required.")
    if prompt_risk.conservative:
        return [
            generate_candidate(
                backend=backend,
                original_prompt=original_prompt,
                lang=languages[0],
                prompt_risk=prompt_risk,
                timeout=timeout,
                max_output_tokens=max_output_tokens,
                token_counter=token_counter,
            )
        ]

    canonical = generate_candidate(
        backend=backend,
        original_prompt=original_prompt,
        lang=CANONICAL_LANGUAGE,
        prompt_risk=prompt_risk,
        timeout=timeout,
        max_output_tokens=max_output_tokens,
        token_counter=token_counter,
        rewrite_source_kind="original",
    )
    return [
        canonical,
        *_generate_language_candidates(
            backend=backend,
            original_prompt=original_prompt,
            rewrite_source_prompt=canonical.text,
            rewrite_source_kind=CANONICAL_LANGUAGE,
            languages=languages,
            prompt_risk=prompt_risk,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
            token_counter=token_counter,
            parallel=parallel,
        ),
    ]


def _generate_language_candidates(
    *,
    backend,
    original_prompt: str,
    rewrite_source_prompt: str,
    rewrite_source_kind: str,
    languages: tuple[str, ...],
    prompt_risk: PromptRisk,
    timeout: int,
    max_output_tokens: int | None,
    token_counter: TokenCounter | None,
    parallel: bool,
) -> list[Candidate]:
    if len(languages) == 1 or not parallel:
        return [
            generate_candidate(
                backend=backend,
                original_prompt=original_prompt,
                rewrite_source_prompt=rewrite_source_prompt,
                rewrite_source_kind=rewrite_source_kind,
                lang=lang,
                prompt_risk=prompt_risk,
                timeout=timeout,
                max_output_tokens=max_output_tokens,
                token_counter=token_counter,
            )
            for lang in languages
        ]

    futures: dict[Future[Candidate], str] = {}
    candidates_by_lang: dict[str, Candidate] = {}
    with ThreadPoolExecutor(max_workers=min(len(languages), MAX_PARALLEL_WORKERS)) as executor:
        for lang in languages:
            future = executor.submit(
                generate_candidate,
                backend=backend,
                original_prompt=original_prompt,
                rewrite_source_prompt=rewrite_source_prompt,
                rewrite_source_kind=rewrite_source_kind,
                lang=lang,
                prompt_risk=prompt_risk,
                timeout=timeout,
                max_output_tokens=max_output_tokens,
                token_counter=token_counter,
            )
            futures[future] = lang
        for future in as_completed(futures):
            candidate = future.result()
            candidates_by_lang[candidate.lang] = candidate
    return [candidates_by_lang[lang] for lang in languages]


def evaluate_candidates(
    *,
    candidates: list[Candidate],
    judge_backend,
    original_prompt: str,
    timeout: int,
) -> None:
    if judge_backend is None:
        for candidate in candidates:
            candidate.valid = is_candidate_valid(candidate)
        return

    eligible = [candidate for candidate in candidates if candidate.literal_check.get("ok")]
    if not eligible:
        return

    sorted_candidates = sorted(eligible, key=candidate_sort_key)
    first_group_size = _first_token_group_size(sorted_candidates)

    _judge_candidate_batch(
        sorted_candidates[:first_group_size],
        judge_backend=judge_backend,
        original_prompt=original_prompt,
        timeout=timeout,
    )
    if any(candidate.valid for candidate in sorted_candidates[:first_group_size]):
        return

    _judge_candidate_batch(
        sorted_candidates[first_group_size:],
        judge_backend=judge_backend,
        original_prompt=original_prompt,
        timeout=timeout,
    )


def _first_token_group_size(candidates: list[Candidate]) -> int:
    first_group = next(
        groupby(
            candidates,
            key=lambda candidate: (
                candidate.token_count if candidate.token_count is not None else 10**9
            ),
        ),
        None,
    )
    if first_group is None:
        return 0
    _, grouped_candidates = first_group
    return sum(1 for _ in grouped_candidates)


def _judge_candidate_batch(
    candidates: list[Candidate],
    *,
    judge_backend,
    original_prompt: str,
    timeout: int,
) -> None:
    if not candidates:
        return
    if len(candidates) == 1:
        candidate = candidates[0]
        verifier = judge_candidate(
            judge_backend=judge_backend,
            original_prompt=original_prompt,
            candidate_text=candidate.text,
            timeout=timeout,
        )
        candidate.verifier = verifier
        candidate.valid = is_candidate_valid(candidate)
        return

    futures: dict[Future[dict[str, Any]], Candidate] = {}
    with ThreadPoolExecutor(max_workers=min(len(candidates), MAX_PARALLEL_WORKERS)) as executor:
        for candidate in candidates:
            future = executor.submit(
                judge_candidate,
                judge_backend=judge_backend,
                original_prompt=original_prompt,
                candidate_text=candidate.text,
                timeout=timeout,
            )
            futures[future] = candidate
        for future in as_completed(futures):
            candidate = futures[future]
            candidate.verifier = future.result()
            candidate.valid = is_candidate_valid(candidate)


def build_backend_token_counter(backend, *, token_timeout: int) -> TokenCounter:
    def _count(text: str) -> tuple[int, str]:
        return backend.count_text_tokens(text, timeout=token_timeout)

    return _count


def build_shared_token_counter(tokenizer_name: str) -> TokenCounter:
    try:
        import tiktoken
    except Exception as exc:
        raise PipelineError("Shared token counting requires tiktoken.") from exc

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


def build_token_counter(config: PipelineConfig, *, backend) -> TokenCounter:
    tokenizer_name = config.tokenizer or ""
    if tokenizer_name:
        return build_shared_token_counter(tokenizer_name)
    token_timeout = min(config.timeout, TOKEN_COUNT_TIMEOUT)
    return build_backend_token_counter(backend, token_timeout=token_timeout)


def count_original_tokens(
    text: str,
    *,
    token_counter: TokenCounter,
) -> tuple[int | None, str]:
    try:
        return token_counter(text)
    except Exception:
        return None, "unavailable"


def generate_candidate(
    *,
    backend,
    original_prompt: str,
    lang: str,
    timeout: int,
    max_output_tokens: int | None,
    token_counter: TokenCounter | None = None,
    prompt_risk: PromptRisk | None = None,
    rewrite_source_prompt: str | None = None,
    rewrite_source_kind: str = "original",
) -> Candidate:
    risk = prompt_risk or classify_prompt(original_prompt)
    source_prompt = rewrite_source_prompt if rewrite_source_prompt is not None else original_prompt
    rewrite_user = build_rewrite_user_prompt(
        source_prompt,
        lang,
        conservative=risk.conservative,
        risk_tags=risk.tags,
    )
    text, generation_meta = backend.generate(
        system_prompt=REWRITE_SYSTEM,
        user_prompt=rewrite_user,
        max_output_tokens=max_output_tokens,
        timeout=timeout,
    )
    candidate = Candidate(
        lang=lang,
        text=strip_code_fences(text).strip(),
        generation_meta={
            **generation_meta,
            "prompt_risk": risk.to_dict(),
            "rewrite_source": rewrite_source_kind,
        },
    )
    language_check = language_shape_check(candidate.lang, candidate.text)
    candidate.generation_meta["language_check"] = language_check
    if not language_check["ok"]:
        candidate.warnings.append(str(language_check["reason"]))
    candidate.literal_check = literal_coverage(original_prompt, candidate.text)
    if token_counter is not None:
        count, count_source = token_counter(candidate.text)
        candidate.token_count = count
        candidate.token_count_source = count_source
    return candidate


def language_shape_check(lang: str, text: str) -> dict[str, Any]:
    if lang != "wenyan":
        return {"ok": True}

    strong_hits = [marker for marker in WENYAN_STRONG_MODERN_MARKERS if marker in text]
    marker_hits = [marker for marker in WENYAN_MODERN_MARKERS if marker in text]
    if strong_hits or len(marker_hits) >= 4:
        return {
            "ok": False,
            "reason": "wenyan candidate looks like modern Chinese",
            "markers": strong_hits + marker_hits,
        }
    return {"ok": True}


def judge_candidate(
    *,
    judge_backend,
    original_prompt: str,
    candidate_text: str,
    timeout: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(JUDGE_PARSE_RETRIES + 1):
        verifier_text, verifier_meta = judge_backend.generate(
            system_prompt=VERIFIER_SYSTEM,
            user_prompt=build_verifier_user_prompt(original_prompt, candidate_text),
            json_schema=VERIFIER_SCHEMA,
            max_output_tokens=None,
            timeout=timeout,
        )
        try:
            verifier = parse_json_response(verifier_text)
        except Exception as exc:
            last_error = exc
            continue
        verifier["_meta"] = verifier_meta
        return verifier

    if last_error is not None:
        raise last_error
    raise RuntimeError("judge_candidate reached an unexpected state")


def is_candidate_valid(candidate: Candidate, *, verifier: dict[str, Any] | None = None) -> bool:
    verifier_payload = candidate.verifier if verifier is None else verifier
    language_check = candidate.generation_meta.get("language_check", {})
    if isinstance(language_check, dict) and language_check.get("ok") is False:
        return False
    if not verifier_payload:
        return bool(candidate.literal_check.get("ok"))
    return bool(
        candidate.literal_check.get("ok")
        and verifier_payload.get("faithful") is True
        and verifier_payload.get("same_task_count") is True
        and verifier_payload.get("same_order") is True
        and not verifier_payload.get("added_info")
        and not verifier_payload.get("ambiguities")
        and not verifier_payload.get("missing_constraints")
        and not verifier_payload.get("missing_literals")
    )
