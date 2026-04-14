from typing import Any

REWRITE_SYSTEM = """You optimize prompts for downstream LLMs.
Your job is to compress prompts without changing their meaning.
Be conservative: if compression risks ambiguity, keep the original detail.
Return only the rewritten prompt, with no commentary.
"""

LANGUAGE_LABELS = {
    "zh": "modern Chinese",
    "wenyan": (
        "Classical Chinese (Wenyan) only when it remains technically precise and does not harm"
        " implementation clarity; otherwise use very terse modern Chinese"
    ),
    "en": "English",
}

DEFAULT_LANGUAGES = ("zh", "wenyan", "en")

VERIFIER_SYSTEM = """You are a strict rewrite auditor.
Compare the original prompt and the candidate rewrite.
Reject the candidate if it drops tasks, constraints, literals, ordering, or actionable clarity.
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
