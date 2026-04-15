from __future__ import annotations

import re
from dataclasses import dataclass

from promptcrab.constants import DEFAULT_LANGUAGES

CONSERVATIVE_LANGUAGES = ("preserve",)

TAG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "verbatim_repeat",
        re.compile(
            r"\b(repeat|reproduce|copy|quote)\b.{0,80}"
            r"\b(exactly|verbatim|without (?:any )?change|unchanged|word for word)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "format_template",
        re.compile(
            r"\b(format below|following format|same format|template|bullet 1|bullet 2)\b"
            r"|\*\s*Bullet\s+\d+|\*\s*\.\.\.",
            re.IGNORECASE,
        ),
    ),
    (
        "literal_marker",
        re.compile(
            r"\b(starting with|starts with|ending with|represented by|separated (?:using|by))\b"
            r"|P\.P\.S|\*\*\*|\[[^\]\n]+\]",
            re.IGNORECASE,
        ),
    ),
    (
        "count_constraint",
        re.compile(
            r"\b(at least|at most|exactly|no more than|minimum|maximum)\s+\d+\b",
            re.IGNORECASE,
        ),
    ),
    (
        "case_sensitive",
        re.compile(
            r"\b(all capital letters|all-caps|uppercase|lowercase|case-sensitive)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "structured_data",
        re.compile(
            r"\b(JSON|YAML|XML|CSV|stack trace|traceback|query parameter|field name|key name)\b"
            r"|[\"'][A-Za-z_][A-Za-z0-9_-]*[\"']\s*:",
            re.IGNORECASE,
        ),
    ),
    (
        "symbol_sensitive",
        re.compile(r"\^|\*\*\*|>=|<=|==|!=|->|=>|[A-Za-z]\s*\*\s*[A-Za-z]"),
    ),
)


@dataclass(frozen=True, slots=True)
class PromptRisk:
    mode: str
    tags: tuple[str, ...]
    reasons: tuple[str, ...]
    languages: tuple[str, ...]

    @property
    def conservative(self) -> bool:
        return self.mode == "conservative"

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "tags": list(self.tags),
            "reasons": list(self.reasons),
            "languages": list(self.languages),
        }


def classify_prompt(prompt: str) -> PromptRisk:
    tags: list[str] = []
    reasons: list[str] = []
    for tag, pattern in TAG_PATTERNS:
        if pattern.search(prompt):
            tags.append(tag)
            reasons.append(_reason_for_tag(tag))

    if tags:
        return PromptRisk(
            mode="conservative",
            tags=tuple(dict.fromkeys(tags)),
            reasons=tuple(dict.fromkeys(reasons)),
            languages=CONSERVATIVE_LANGUAGES,
        )

    return PromptRisk(
        mode="normal",
        tags=(),
        reasons=(),
        languages=DEFAULT_LANGUAGES,
    )


def _reason_for_tag(tag: str) -> str:
    return {
        "verbatim_repeat": "Prompt asks for exact/verbatim text preservation.",
        "format_template": "Prompt includes a format template or bullet scaffold.",
        "literal_marker": "Prompt includes exact markers, separators, or bracket literals.",
        "count_constraint": "Prompt includes numeric output constraints.",
        "case_sensitive": "Prompt includes case-sensitive output constraints.",
        "structured_data": "Prompt includes structured data or execution-sensitive fields.",
        "symbol_sensitive": "Prompt includes symbols that should not be normalized.",
    }[tag]
