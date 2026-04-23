import threading

import pytest

from promptcrab.constants import CANONICAL_LANGUAGE
from promptcrab.errors import PipelineError
from promptcrab.models import Candidate, PipelineConfig
from promptcrab.pipeline import (
    _evaluate_candidate,
    choose_best,
    generate_candidates,
    is_candidate_valid,
    judge_candidate,
    language_shape_check,
    run_pipeline,
)
from promptcrab.preflight import classify_prompt


def test_choose_best_prefers_smallest_valid_candidate() -> None:
    larger = Candidate(lang="zh", text="a", token_count=10, valid=True)
    smaller = Candidate(lang="en", text="b", token_count=5, valid=True)

    best_text, best_candidate, reasons = choose_best([larger, smaller], "original")

    assert best_text == "b"
    assert best_candidate is smaller
    assert reasons == []


def test_choose_best_ignores_language_and_picks_smallest_valid_candidate() -> None:
    zh = Candidate(lang="zh", text="zh", token_count=125, valid=True)
    wenyan = Candidate(lang="wenyan", text="wenyan", token_count=123, valid=True)

    best_text, best_candidate, reasons = choose_best([wenyan, zh], "為什麼資料卡住？")

    assert best_text == "wenyan"
    assert best_candidate is wenyan
    assert reasons == []


def test_choose_best_falls_back_to_original_when_all_invalid() -> None:
    invalid = Candidate(
        lang="zh",
        text="candidate",
        token_count=5,
        valid=False,
        verifier={"faithful": False},
        literal_check={"ok": False, "missing": {"numbers": ["42"]}},
    )

    best_text, best_candidate, reasons = choose_best([invalid], "original")

    assert best_text == "original"
    assert best_candidate is None
    assert reasons == ["zh: invalid; missing literals={'numbers': ['42']}; faithful=False"]


def test_choose_best_reports_judge_ambiguities_when_invalid() -> None:
    invalid = Candidate(
        lang="zh",
        text="candidate",
        token_count=5,
        valid=False,
        literal_check={"ok": True, "missing": {}},
        verifier={
            "faithful": True,
            "same_task_count": True,
            "same_order": True,
            "missing_literals": [],
            "missing_constraints": [],
            "added_info": [],
            "ambiguities": ["output format is less specific"],
        },
    )

    best_text, best_candidate, reasons = choose_best([invalid], "original")

    assert best_text == "original"
    assert best_candidate is None
    assert reasons == [
        "zh: invalid; faithful=True; ambiguities=['output format is less specific']"
    ]


def test_candidate_with_judge_ambiguities_is_invalid() -> None:
    candidate = Candidate(
        lang="zh",
        text="candidate",
        literal_check={"ok": True, "missing": {}},
        verifier={
            "faithful": True,
            "same_task_count": True,
            "same_order": True,
            "missing_literals": [],
            "missing_constraints": [],
            "added_info": [],
            "ambiguities": ["unclear output shape"],
        },
    )

    assert is_candidate_valid(candidate) is False


def test_wenyan_candidate_with_modern_chinese_markers_is_invalid() -> None:
    check = language_shape_check(
        "wenyan",
        "你必須分析不同換股特性或投資組合檔數對策略表現的影響，例如月初換股。",
    )
    candidate = Candidate(
        lang="wenyan",
        text="你必須分析不同換股特性或投資組合檔數對策略表現的影響，例如月初換股。",
        literal_check={"ok": True, "missing": {}},
        generation_meta={"language_check": check},
    )

    assert check["ok"] is False
    assert is_candidate_valid(candidate) is False


def test_generate_candidates_rejects_empty_language_list() -> None:
    with pytest.raises(PipelineError, match="At least one rewrite language"):
        generate_candidates(
            backend=object(),
            original_prompt="prompt",
            languages=(),
            prompt_risk=classify_prompt("prompt"),
            timeout=1,
            max_output_tokens=None,
        )


def test_generate_candidates_uses_canonical_prompt_as_translation_source() -> None:
    class SourceTrackingBackend:
        def __init__(self) -> None:
            self.user_prompts: list[str] = []

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            json_schema=None,
            max_output_tokens=None,
            timeout: int = 300,
        ):
            del system_prompt, json_schema, max_output_tokens, timeout
            self.user_prompts.append(user_prompt)
            if "the original language only" in user_prompt:
                return "Fix the thing 42", {}
            if "modern Chinese" in user_prompt:
                return "修正 thing 42", {}
            return "Fix thing 42", {}

    backend = SourceTrackingBackend()

    candidates = generate_candidates(
        backend=backend,
        original_prompt="Fix teh thing 42",
        languages=("zh", "en"),
        prompt_risk=classify_prompt("Fix teh thing 42"),
        timeout=1,
        max_output_tokens=None,
        token_counter=lambda text: (len(text), "dummy"),
        parallel=False,
    )

    assert [candidate.lang for candidate in candidates] == [CANONICAL_LANGUAGE, "zh", "en"]
    assert "Fix teh thing 42" in backend.user_prompts[0]
    assert "Fix the thing 42" in backend.user_prompts[1]
    assert "Fix the thing 42" in backend.user_prompts[2]


def test_generate_candidates_does_not_fallback_to_original_when_canonical_is_literal_invalid(
) -> None:
    class SourceTrackingBackend:
        def __init__(self) -> None:
            self.user_prompts: list[str] = []

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            json_schema=None,
            max_output_tokens=None,
            timeout: int = 300,
        ):
            del system_prompt, json_schema, max_output_tokens, timeout
            self.user_prompts.append(user_prompt)
            if "the original language only" in user_prompt:
                return "Fix the thing", {}
            return "修正 thing", {}

    backend = SourceTrackingBackend()

    candidates = generate_candidates(
        backend=backend,
        original_prompt="Fix teh thing 42",
        languages=("zh",),
        prompt_risk=classify_prompt("Fix teh thing 42"),
        timeout=1,
        max_output_tokens=None,
        token_counter=lambda text: (len(text), "dummy"),
        parallel=False,
    )

    assert [candidate.lang for candidate in candidates] == [CANONICAL_LANGUAGE, "zh"]
    assert candidates[0].literal_check["ok"] is False
    assert "Fix teh thing 42" in backend.user_prompts[0]
    assert "Fix the thing" in backend.user_prompts[1]
    assert "Fix teh thing 42" not in backend.user_prompts[1]


class DummyRewriteBackend:
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema=None,
        max_output_tokens=None,
        timeout: int = 300,
    ):
        self.calls += 1
        return "```text\nrewritten\n```", {}

    def count_text_tokens(self, text: str, timeout: int = 120):
        return len(text), "dummy"


class DummyJudgeBackend:
    def __init__(self) -> None:
        self.calls = 0
        self.last_max_output_tokens = "unset"

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema=None,
        max_output_tokens=None,
        timeout: int = 300,
    ):
        self.calls += 1
        self.last_max_output_tokens = max_output_tokens
        return (
            '{"faithful": true, "same_task_count": true, "same_order": true, '
            '"missing_literals": [], "missing_constraints": [], "added_info": [], '
            '"ambiguities": [], "notes": []}',
            {},
        )


class FlakyJudgeBackend:
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema=None,
        max_output_tokens=None,
        timeout: int = 300,
    ):
        self.calls += 1
        if self.calls == 1:
            return '{"faithful": true, "same_task_count": true', {}
        return (
            '{"faithful": true, "same_task_count": true, "same_order": true, '
            '"missing_literals": [], "missing_constraints": [], "added_info": [], '
            '"ambiguities": [], "notes": []}',
            {},
        )


def test_evaluate_candidate_strips_outer_code_fences_and_uses_judge_backend() -> None:
    rewrite_backend = DummyRewriteBackend()
    judge_backend = DummyJudgeBackend()
    candidate = _evaluate_candidate(
        backend=rewrite_backend,
        judge_backend=judge_backend,
        original_prompt="original",
        lang="zh",
        timeout=1,
        max_output_tokens=999,
        token_counter=lambda text: (len(text), "dummy"),
    )

    assert candidate.text == "rewritten"
    assert rewrite_backend.calls == 1
    assert judge_backend.calls == 1
    assert judge_backend.last_max_output_tokens is None


def test_evaluate_candidate_without_judge_uses_literal_check_only() -> None:
    rewrite_backend = DummyRewriteBackend()

    candidate = _evaluate_candidate(
        backend=rewrite_backend,
        judge_backend=None,
        original_prompt="rewritten",
        lang="zh",
        timeout=1,
        max_output_tokens=None,
        token_counter=lambda text: (len(text), "dummy"),
    )

    assert candidate.text == "rewritten"
    assert candidate.verifier == {}
    assert candidate.valid is True


def test_judge_candidate_retries_when_judge_returns_invalid_json() -> None:
    backend = FlakyJudgeBackend()

    verifier = judge_candidate(
        judge_backend=backend,
        original_prompt="original",
        candidate_text="candidate",
        timeout=1,
    )

    assert backend.calls == 2
    assert verifier["faithful"] is True


def test_run_pipeline_uses_distinct_codex_reasoning_effort_for_judge(monkeypatch) -> None:
    seen_efforts: list[str | None] = []

    class FakeBackend:
        def __init__(self, role: str) -> None:
            self.role = role
            self.name = role
            self.model = role

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            json_schema=None,
            max_output_tokens=None,
            timeout: int = 300,
        ):
            if json_schema is None:
                return "rewritten", {}
            return (
                '{"faithful": true, "same_task_count": true, "same_order": true, '
                '"missing_literals": [], "missing_constraints": [], "added_info": [], '
                '"ambiguities": [], "notes": []}',
                {},
            )

        def count_text_tokens(self, text: str, timeout: int = 120):
            return len(text), "dummy"

    def fake_build_backend(config: PipelineConfig):
        seen_efforts.append(config.codex_reasoning_effort)
        return FakeBackend(config.model)

    monkeypatch.setattr("promptcrab.pipeline.build_backend", fake_build_backend)

    result = run_pipeline(
        PipelineConfig(
            backend="codex_cli",
            model="rewrite-model",
            prompt="prompt",
            judge_backend="codex_cli",
            judge_model="judge-model",
            codex_reasoning_effort="medium",
            judge_codex_reasoning_effort="high",
        )
    )

    assert seen_efforts[:2] == ["medium", "high"]
    assert result.judge_model == "judge-model"


def test_run_pipeline_prefers_shared_tokenizer_by_default(monkeypatch) -> None:
    class FakeBackend:
        name = "fake"
        model = "fake-model"

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            json_schema=None,
            max_output_tokens=None,
            timeout: int = 300,
        ):
            return "rewritten", {}

        def count_text_tokens(self, text: str, timeout: int = 120):
            raise AssertionError("backend-native token counter should not be called")

    monkeypatch.setattr("promptcrab.pipeline.build_backend", lambda config: FakeBackend())

    result = run_pipeline(
        PipelineConfig(
            backend="codex_cli",
            model="rewrite-model",
            prompt="prompt",
        )
    )

    assert result.original_token_count is not None
    assert result.original_token_count_source == "tiktoken_encoding:o200k_base"
    assert all(
        candidate.token_count_source == "tiktoken_encoding:o200k_base"
        for candidate in result.candidates
    )


def test_run_pipeline_can_disable_shared_tokenizer(monkeypatch) -> None:
    count_calls: list[str] = []

    class FakeBackend:
        name = "fake"
        model = "fake-model"

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            json_schema=None,
            max_output_tokens=None,
            timeout: int = 300,
        ):
            return "rewritten", {}

        def count_text_tokens(self, text: str, timeout: int = 120):
            count_calls.append(text)
            return len(text), "backend-native"

    monkeypatch.setattr("promptcrab.pipeline.build_backend", lambda config: FakeBackend())

    result = run_pipeline(
        PipelineConfig(
            backend="codex_cli",
            model="rewrite-model",
            prompt="prompt",
            tokenizer=None,
        )
    )

    assert count_calls
    assert result.original_token_count_source == "backend-native"


def test_run_pipeline_generates_language_candidates_in_parallel(monkeypatch) -> None:
    barrier = threading.Barrier(3, timeout=1)

    class FakeBackend:
        name = "fake"
        model = "fake-model"

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            json_schema=None,
            max_output_tokens=None,
            timeout: int = 300,
        ):
            if "the original language only" in user_prompt:
                return "canonical", {}
            barrier.wait()
            return "rewritten", {}

        def count_text_tokens(self, text: str, timeout: int = 120):
            return len(text), "backend-native"

    monkeypatch.setattr("promptcrab.pipeline.build_backend", lambda config: FakeBackend())

    result = run_pipeline(
        PipelineConfig(
            backend="codex_cli",
            model="rewrite-model",
            prompt="prompt",
            tokenizer=None,
        )
    )

    assert len(result.candidates) == 4
    assert result.candidates[0].lang == CANONICAL_LANGUAGE
    assert all(candidate.valid for candidate in result.candidates)


def test_run_pipeline_skips_judging_literal_invalid_candidates_and_stops_after_best(
    monkeypatch,
) -> None:
    class FakeRewriteBackend:
        name = "rewrite"
        model = "rewrite-model"

        def __init__(self) -> None:
            self.user_prompts: list[str] = []

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            json_schema=None,
            max_output_tokens=None,
            timeout: int = 300,
        ):
            self.user_prompts.append(user_prompt)
            if user_prompt.startswith("Rewrite the ORIGINAL_PROMPT into the original language"):
                return "canonical keep 42", {}
            if user_prompt.startswith("Rewrite the ORIGINAL_PROMPT into modern Chinese."):
                return "keep 42", {}
            if user_prompt.startswith("Rewrite the ORIGINAL_PROMPT into Classical Chinese"):
                return "long keep 42", {}
            return "drop", {}

        def count_text_tokens(self, text: str, timeout: int = 120):
            return len(text), "backend-native"

    class FakeJudgeBackend:
        name = "judge"
        model = "judge-model"

        def __init__(self) -> None:
            self.seen_candidates: list[str] = []

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            json_schema=None,
            max_output_tokens=None,
            timeout: int = 300,
        ):
            self.seen_candidates.append(user_prompt)
            return (
                '{"faithful": true, "same_task_count": true, "same_order": true, '
                '"missing_literals": [], "missing_constraints": [], "added_info": [], '
                '"ambiguities": [], "notes": []}',
                {},
            )

    rewrite_backend = FakeRewriteBackend()
    judge_backend = FakeJudgeBackend()

    def fake_build_backend(config: PipelineConfig):
        if config.model == "judge-model":
            return judge_backend
        return rewrite_backend

    monkeypatch.setattr("promptcrab.pipeline.build_backend", fake_build_backend)

    result = run_pipeline(
        PipelineConfig(
            backend="codex_cli",
            model="rewrite-model",
            prompt="keep 42",
            judge_backend="codex_cli",
            judge_model="judge-model",
            tokenizer=None,
        )
    )

    assert len(judge_backend.seen_candidates) == 1
    assert result.best_lang == "zh"
    assert result.candidates[0].lang == CANONICAL_LANGUAGE
    assert result.candidates[0].verifier == {}
    assert result.candidates[1].valid is True
    assert result.candidates[2].verifier == {}
    assert result.candidates[3].verifier == {}
    assert result.candidates[3].literal_check["ok"] is False
    assert "canonical keep 42" in rewrite_backend.user_prompts[1]
