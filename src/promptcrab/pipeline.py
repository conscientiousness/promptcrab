from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from promptcrab.backends import build_backend
from promptcrab.constants import (
    REWRITE_SYSTEM,
    VERIFIER_SCHEMA,
    VERIFIER_SYSTEM,
)
from promptcrab.literal_checks import literal_coverage
from promptcrab.models import Candidate, PipelineConfig, PipelineResult
from promptcrab.parsing import parse_json_response, strip_code_fences
from promptcrab.preflight import PromptRisk, classify_prompt
from promptcrab.prompts import build_rewrite_user_prompt, build_verifier_user_prompt

TOKEN_COUNT_TIMEOUT = 120
JUDGE_PARSE_RETRIES = 2
TokenCounter = Callable[[str], tuple[int, str]]


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
    token_timeout = min(config.timeout, TOKEN_COUNT_TIMEOUT)
    token_counter = build_backend_token_counter(backend, token_timeout=token_timeout)
    prompt_risk = classify_prompt(config.prompt)

    candidates: list[Candidate] = []
    for lang in prompt_risk.languages:
        candidate = _evaluate_candidate(
            backend=backend,
            judge_backend=judge_backend,
            original_prompt=config.prompt,
            lang=lang,
            prompt_risk=prompt_risk,
            timeout=config.timeout,
            max_output_tokens=config.max_output_tokens,
            token_counter=token_counter,
        )
        candidates.append(candidate)

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


def build_backend_token_counter(backend, *, token_timeout: int) -> TokenCounter:
    def _count(text: str) -> tuple[int, str]:
        return backend.count_text_tokens(text, timeout=token_timeout)

    return _count


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
) -> Candidate:
    risk = prompt_risk or classify_prompt(original_prompt)
    rewrite_user = build_rewrite_user_prompt(
        original_prompt,
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
        generation_meta={**generation_meta, "prompt_risk": risk.to_dict()},
    )
    candidate.literal_check = literal_coverage(original_prompt, candidate.text)
    if token_counter is not None:
        count, count_source = token_counter(candidate.text)
        candidate.token_count = count
        candidate.token_count_source = count_source
    return candidate


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
    if not verifier_payload:
        return bool(candidate.literal_check.get("ok"))
    return bool(
        candidate.literal_check.get("ok")
        and verifier_payload.get("faithful") is True
        and verifier_payload.get("same_task_count") is True
        and verifier_payload.get("same_order") is True
        and not verifier_payload.get("added_info")
        and not verifier_payload.get("missing_constraints")
        and not verifier_payload.get("missing_literals")
    )
