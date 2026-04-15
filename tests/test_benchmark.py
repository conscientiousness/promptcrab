import json

from promptcrab.benchmark import (
    DEFAULT_DATASETS,
    BenchmarkCase,
    parse_hard_case_cases,
    parse_mt_bench_cases,
    run_case_once,
    sample_cases,
    summarize_benchmark,
)


def test_parse_mt_bench_cases_expands_each_turn() -> None:
    raw = "\n".join(
        [
            json.dumps(
                {
                    "question_id": 81,
                    "category": "writing",
                    "turns": ["first prompt", "second prompt"],
                }
            ),
            json.dumps(
                {
                    "question_id": 82,
                    "category": "reasoning",
                    "turns": ["third prompt"],
                }
            ),
        ]
    )

    cases = parse_mt_bench_cases(raw, "https://example.test/mt_bench.jsonl")

    assert [case.case_id for case in cases] == [
        "mt_bench:81:1",
        "mt_bench:81:2",
        "mt_bench:82:1",
    ]
    assert [case.category for case in cases] == ["writing", "writing", "reasoning"]


def test_sample_cases_spreads_across_categories() -> None:
    cases = [
        BenchmarkCase(
            case_id=f"case-{index}",
            dataset="demo",
            prompt="prompt",
            source_url="https://example.test",
            title=f"Case {index}",
            category=category,
        )
        for index, category in enumerate(
            ["alpha", "alpha", "beta", "beta", "gamma", "gamma"],
            start=1,
        )
    ]

    sampled = sample_cases(cases, max_cases=4, seed=1)

    assert len(sampled) == 4
    assert {case.category for case in sampled} == {"alpha", "beta", "gamma"}


def test_default_datasets_include_builtin_hard_cases() -> None:
    assert DEFAULT_DATASETS[0] == "hard_cases"


def test_parse_hard_case_cases_returns_literal_format_suite() -> None:
    cases = parse_hard_case_cases("", "builtin:hard_cases")

    assert len(cases) == 5
    assert {case.dataset for case in cases} == {"hard_cases"}
    assert {case.category for case in cases} == {
        "verbatim_repeat",
        "format_template",
        "literal_marker",
        "separator_case_count",
        "symbol_structured_data",
    }


class FakeRewriteBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls = 0
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
        output = self.outputs[self.calls]
        self.calls += 1
        return output, {}


class FakeJudgeBackend:
    def __init__(self, invalid_candidates: set[str]) -> None:
        self.invalid_candidates = invalid_candidates
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
        candidate = user_prompt.split("<<<CANDIDATE\n", 1)[1].split("\nCANDIDATE\n>>>", 1)[0]
        valid = candidate not in self.invalid_candidates
        return (
            json.dumps(
                {
                    "faithful": valid,
                    "same_task_count": valid,
                    "same_order": valid,
                    "missing_literals": [],
                    "missing_constraints": [] if valid else ["constraint"],
                    "added_info": [],
                    "ambiguities": [],
                    "notes": [],
                }
            ),
            {},
        )


def test_run_case_once_uses_one_rewrite_panel_for_multiple_judges() -> None:
    rewrite_backend = FakeRewriteBackend(["short winner", "invalid choice", "long valid candidate"])
    judge_one = FakeJudgeBackend({"invalid choice"})
    judge_two = FakeJudgeBackend({"invalid choice"})
    case = BenchmarkCase(
        case_id="demo-1",
        dataset="demo",
        prompt="Original prompt text",
        source_url="https://example.test",
        title="Demo case",
        category="demo",
    )

    result = run_case_once(
        case=case,
        trial=1,
        rewrite_backend=rewrite_backend,
        judge_backends={
            "judge_one": judge_one,
            "judge_two": judge_two,
        },
        token_counter=lambda text: (len(text.split()), "shared_test_counter"),
        timeout=1,
        max_output_tokens=None,
    )

    assert rewrite_backend.calls == 3
    assert judge_one.calls == 3
    assert judge_two.calls == 3
    assert result["consensus"]["pass"] is True
    assert result["consensus"]["best_lang"] == "zh"
    assert result["before_gate"]["best_lang"] == "zh"
    assert result["prompt_risk"]["mode"] == "normal"
    assert result["judges"]["judge_one"]["best_lang"] == "zh"
    assert result["judges"]["judge_two"]["best_lang"] == "zh"


def test_run_case_once_uses_conservative_single_candidate_for_literal_sensitive_prompt() -> None:
    prompt = (
        "Repeat exactly this question without changing any words, then answer it: "
        "What is the name of the actor who played Gandalf in Lord of the Rings?"
    )
    rewrite_backend = FakeRewriteBackend([prompt])
    judge = FakeJudgeBackend(set())
    case = BenchmarkCase(
        case_id="hard-1",
        dataset="hard_cases",
        prompt=prompt,
        source_url="builtin:hard_cases",
        title="Hard case",
        category="verbatim_repeat",
    )

    result = run_case_once(
        case=case,
        trial=1,
        rewrite_backend=rewrite_backend,
        judge_backends={"judge": judge},
        token_counter=lambda text: (len(text.split()), "shared_test_counter"),
        timeout=1,
        max_output_tokens=None,
    )

    assert rewrite_backend.calls == 1
    assert judge.calls == 1
    assert result["candidates"][0]["lang"] == "preserve"
    assert result["prompt_risk"]["mode"] == "conservative"
    assert "verbatim_repeat" in result["prompt_risk"]["tags"]
    assert "do not translate" in rewrite_backend.user_prompts[0]


def test_summarize_benchmark_reports_rates_and_agreement() -> None:
    results = [
        {
            "dataset": "mt_bench",
            "before_gate": {"token_reduction_ratio": 0.30},
            "judges": {"judge_a": {"pass": True}, "judge_b": {"pass": True}},
            "consensus": {"pass": True, "token_reduction_ratio": 0.20},
        },
        {
            "dataset": "mt_bench",
            "before_gate": {"token_reduction_ratio": 0.40},
            "judges": {"judge_a": {"pass": True}, "judge_b": {"pass": False}},
            "consensus": {"pass": False, "token_reduction_ratio": None},
        },
        {
            "dataset": "ifeval",
            "before_gate": {"token_reduction_ratio": 0.50},
            "judges": {"judge_a": {"pass": False}, "judge_b": {"pass": False}},
            "consensus": {"pass": False, "token_reduction_ratio": None},
        },
        {
            "dataset": "ifeval",
            "before_gate": {"token_reduction_ratio": 0.15},
            "judges": {"judge_a": {"pass": True}, "judge_b": {"pass": True}},
            "consensus": {"pass": True, "token_reduction_ratio": 0.10},
        },
    ]

    summary = summarize_benchmark(
        results,
        judge_labels=["judge_a", "judge_b"],
        bootstrap_samples=50,
        seed=3,
    )

    assert summary["panel_runs"] == 4
    assert summary["consensus_pass_rate"]["successes"] == 2
    assert summary["judge_pass_rates"]["judge_a"]["successes"] == 3
    assert summary["before_gate_token_reduction"]["count"] == 4
    assert summary["after_gate_token_reduction"]["count"] == 2
    assert summary["consensus_token_reduction"]["count"] == 2
    assert summary["judge_agreement"][0]["agreement_rate"] == 0.75
    assert summary["by_dataset"]["mt_bench"]["panel_runs"] == 2
    assert summary["by_dataset"]["mt_bench"]["before_gate_token_reduction"]["count"] == 2
