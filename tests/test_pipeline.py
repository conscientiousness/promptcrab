from promptcrab.models import Candidate, PipelineConfig
from promptcrab.pipeline import _evaluate_candidate, choose_best, judge_candidate, run_pipeline


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
