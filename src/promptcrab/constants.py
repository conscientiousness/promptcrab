from typing import Any

REWRITE_SYSTEM = """You optimize prompts for downstream LLMs.
Your job is to improve prompt clarity, structure, and actionability before reducing tokens.
Fix obvious prose-level typos or sentence issues only when doing so cannot alter literals,
constraints, or execution-sensitive wording.
Be conservative: if compression risks ambiguity or weakens the prompt, keep the detail.
Return only the rewritten prompt, with no commentary.
"""

LANGUAGE_LABELS = {
    "canonical": (
        "the original language only. Do not translate. Produce a canonical quality rewrite"
        " that fixes ordinary prose-level typos, grammar, sentence flow, task framing, and"
        " output expectations while preserving all execution-sensitive wording"
    ),
    "preserve": (
        "the original language only. Do not translate. Use a conservative copy-edit that"
        " preserves literal text, formatting templates, markers, separators, symbols, and"
        " quoted/verbatim spans exactly"
    ),
    "zh": "modern Chinese",
    "wenyan": (
        "Classical Chinese (Wenyan). Use actual Wenyan; do not fall back to modern Chinese"
    ),
    "en": "English",
}

CANONICAL_LANGUAGE = "canonical"
DEFAULT_LANGUAGES = ("zh", "wenyan", "en")
DEFAULT_SHARED_TOKENIZER = "o200k_base"

VERIFIER_SYSTEM = """You are a strict rewrite auditor.
Compare the original prompt and the candidate rewrite.
Reject the candidate if it drops tasks, constraints, literals, ordering, actionable clarity,
or introduces ambiguity.
Return JSON only.
"""

VERIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "faithful": {"type": "boolean"},
        "same_task_count": {"type": "boolean"},
        "same_order": {"type": "boolean"},
        "missing_literals": {"type": "array", "items": {"type": "string"}},
        "missing_constraints": {"type": "array", "items": {"type": "string"}},
        "added_info": {"type": "array", "items": {"type": "string"}},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "faithful",
        "same_task_count",
        "same_order",
        "missing_literals",
        "missing_constraints",
        "added_info",
        "ambiguities",
        "notes",
    ],
}
