from __future__ import annotations

import time
from dataclasses import replace

from promptcrab.backends import build_backend
from promptcrab.constants import (
    DEFAULT_LANGUAGES,
    REWRITE_SYSTEM,
    VERIFIER_SCHEMA,
    VERIFIER_SYSTEM,
)
from promptcrab.literal_checks import literal_coverage
from promptcrab.models import Candidate, PipelineConfig, PipelineResult
from promptcrab.parsing import parse_json_response, strip_code_fences
from promptcrab.prompts import build_rewrite_user_prompt, build_verifier_user_prompt

TOKEN_COUNT_TIMEOUT = 120


def choose_best(
    candidates: list[Candidate],
    original_prompt: str,
) -> tuple[str, Candidate | None, list[str]]:
    valid = [
        candidate
        for candidate in candidates
        if candidate.valid and candidate.token_count is not None
    ]
    valid.sort(
        key=lambda candidate: (
            candidate.token_count or 10**9,
            candidate.ambiguity_count(),
            len(candidate.text),
        )
    )
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

    candidates: list[Candidate] = []
    for lang in DEFAULT_LANGUAGES:
        candidate = _evaluate_candidate(
        backend=backend,
        judge_backend=judge_backend,
            original_prompt=config.prompt,
            lang=lang,
            timeout=config.timeout,
            token_timeout=token_timeout,
            max_output_tokens=config.max_output_tokens,
        )
        candidates.append(candidate)

    try:
        original_token_count, original_token_source = backend.count_text_tokens(
            config.prompt,
            timeout=token_timeout,
        )
    except Exception:
        original_token_count, original_token_source = None, "unavailable"

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
    )


def _evaluate_candidate(
    *,
    backend,
    judge_backend,
    original_prompt: str,
    lang: str,
    timeout: int,
    token_timeout: int,
    max_output_tokens: int | None,
) -> Candidate:
    rewrite_user = build_rewrite_user_prompt(original_prompt, lang)
    text, generation_meta = backend.generate(
        system_prompt=REWRITE_SYSTEM,
        user_prompt=rewrite_user,
        max_output_tokens=max_output_tokens,
        timeout=timeout,
    )

    candidate = Candidate(
        lang=lang,
        text=strip_code_fences(text).strip(),
        generation_meta=generation_meta,
    )
    candidate.literal_check = literal_coverage(original_prompt, candidate.text)

    if judge_backend is not None:
        verifier_text, verifier_meta = judge_backend.generate(
            system_prompt=VERIFIER_SYSTEM,
            user_prompt=build_verifier_user_prompt(original_prompt, candidate.text),
            json_schema=VERIFIER_SCHEMA,
            max_output_tokens=None,
            timeout=timeout,
        )
        verifier = parse_json_response(verifier_text)
        verifier["_meta"] = verifier_meta
        candidate.verifier = verifier

    count, count_source = backend.count_text_tokens(candidate.text, timeout=token_timeout)
    candidate.token_count = count
    candidate.token_count_source = count_source
    candidate.valid = _is_valid_candidate(candidate)
    return candidate


def _is_valid_candidate(candidate: Candidate) -> bool:
    if not candidate.verifier:
        return bool(candidate.literal_check.get("ok"))
    return bool(
        candidate.literal_check.get("ok")
        and candidate.verifier.get("faithful") is True
        and candidate.verifier.get("same_task_count") is True
        and candidate.verifier.get("same_order") is True
        and not candidate.verifier.get("added_info")
        and not candidate.verifier.get("missing_constraints")
        and not candidate.verifier.get("missing_literals")
    )
