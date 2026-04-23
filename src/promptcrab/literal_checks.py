from __future__ import annotations

import re
from typing import Any

URL_PATTERN = re.compile(r"https?://[^\s`\"'>)]+")
CODE_SPAN_PATTERN = re.compile(r"`([^`\n]+)`")


def dedupe_keep_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def extract_code_spans(prompt: str) -> list[str]:
    return dedupe_keep_order(
        [
            match.group(1).strip()
            for match in CODE_SPAN_PATTERN.finditer(prompt)
            if match.group(1).strip()
        ]
    )


def extract_ascii_terms(prompt: str) -> list[str]:
    del prompt
    return []


def extract_protected_literals(prompt: str) -> dict[str, list[str]]:
    urls = URL_PATTERN.findall(prompt)
    hyphen_ids = re.findall(r"\b\d{2,}(?:-\d{2,})+\b", prompt)
    node_ids = re.findall(r"\bnode-id\s*=\s*[^\s`]+", prompt)
    image_refs = re.findall(r"\[Image\s*#\d+\]", prompt)
    code_spans = extract_code_spans(prompt)
    quoted_keys = re.findall(r'["\']([A-Za-z_][A-Za-z0-9_-]*)["\']\s*:', prompt)
    bare_keys = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b\s*:", prompt)
    numbers = re.findall(r"\b\d+\b", prompt)
    single_digits = {str(number) for number in range(10)}
    filtered_numbers = [
        number for number in numbers if f"/{number}" not in prompt or number in single_digits
    ]
    return {
        "urls": dedupe_keep_order(urls),
        "hyphen_ids": dedupe_keep_order(hyphen_ids),
        "node_ids": dedupe_keep_order(node_ids),
        "image_refs": dedupe_keep_order(image_refs),
        "code_spans": code_spans,
        "ascii_terms": extract_ascii_terms(prompt),
        "keys": dedupe_keep_order(quoted_keys + bare_keys),
        "numbers": dedupe_keep_order(filtered_numbers),
    }


def boundary_contains(text: str, token: str) -> bool:
    if not token:
        return True
    if token.isdigit():
        return re.search(rf"(?<!\d){re.escape(token)}(?!\d)", text) is not None
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", token):
        pattern = rf"(?<![A-Za-z0-9_-]){re.escape(token)}(?![A-Za-z0-9_-])"
        return re.search(pattern, text) is not None
    return token in text


def literal_coverage(original_prompt: str, candidate_prompt: str) -> dict[str, Any]:
    protected = extract_protected_literals(original_prompt)
    missing: dict[str, list[str]] = {}
    for category, items in protected.items():
        current_missing = [item for item in items if not boundary_contains(candidate_prompt, item)]
        if current_missing:
            missing[category] = current_missing
    missing_total = sum(len(items) for items in missing.values())
    return {
        "protected": protected,
        "missing": missing,
        "ok": missing_total == 0,
    }
