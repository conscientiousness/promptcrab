from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

BackendName = Literal["minimax", "gemini", "gemini_cli", "codex_cli", "opencode_cli"]


@dataclass(slots=True)
class Candidate:
    lang: str
    text: str
    generation_meta: dict[str, Any] = field(default_factory=dict)
    verifier: dict[str, Any] = field(default_factory=dict)
    literal_check: dict[str, Any] = field(default_factory=dict)
    token_count: int | None = None
    token_count_source: str = ""
    valid: bool = False
    warnings: list[str] = field(default_factory=list)

    def ambiguity_count(self) -> int:
        value = self.verifier.get("ambiguities", [])
        return len(value) if isinstance(value, list) else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lang": self.lang,
            "text": self.text,
            "token_count": self.token_count,
            "token_count_source": self.token_count_source,
            "valid": self.valid,
            "literal_check": self.literal_check,
            "verifier": {key: value for key, value in self.verifier.items() if key != "_meta"},
        }


@dataclass(slots=True)
class PipelineConfig:
    backend: BackendName
    model: str
    prompt: str
    judge_backend: BackendName | None = None
    judge_model: str | None = None
    show_all: bool = False
    json_output: bool = False
    write_best_to: Path | None = None
    timeout: int = 300
    max_output_tokens: int | None = None
    minimax_api_key: str | None = None
    minimax_base_url: str = "https://api.minimax.io/v1"
    gemini_api_key: str | None = None
    gemini_executable: str = "gemini"
    codex_executable: str = "codex"
    opencode_executable: str = "opencode"
    codex_reasoning_effort: str | None = None
    judge_codex_reasoning_effort: str | None = None


@dataclass(slots=True)
class PipelineResult:
    backend: str
    model: str
    judge_backend: str | None
    judge_model: str | None
    original_prompt: str
    original_token_count: int | None
    original_token_count_source: str
    candidates: list[Candidate]
    best_prompt: str
    best_lang: str | None
    best_token_count: int | None
    fallback_to_original: bool
    fallback_reasons: list[str]
    generated_at_unix: int
    prompt_risk: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "model": self.model,
            "judge_backend": self.judge_backend,
            "judge_model": self.judge_model,
            "original_prompt": self.original_prompt,
            "original_token_count": self.original_token_count,
            "original_token_count_source": self.original_token_count_source,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "best_prompt": self.best_prompt,
            "best_lang": self.best_lang,
            "best_token_count": self.best_token_count,
            "fallback_to_original": self.fallback_to_original,
            "fallback_reasons": self.fallback_reasons,
            "generated_at_unix": self.generated_at_unix,
            "prompt_risk": self.prompt_risk,
        }
