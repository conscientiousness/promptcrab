from __future__ import annotations

import json
from typing import Any

from promptcrab.errors import PipelineError


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = strip_code_fences(text).strip()
    for candidate in [cleaned, extract_first_json_object(cleaned)]:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise PipelineError(f"Could not parse JSON from model response:\n{text}")


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text


def extract_first_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


def extract_gemini_cli_result(stdout: str) -> tuple[str, dict[str, Any]]:
    cleaned = stdout.strip()
    for candidate in [cleaned, extract_first_json_object(cleaned)]:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            response = parsed.get("response")
            if isinstance(response, str):
                return response, parsed
            if response is not None:
                return stringify_unknown_content(response), parsed
    raise PipelineError(f"Could not parse Gemini CLI JSON response:\n{stdout}")


def extract_opencode_result(stdout: str) -> tuple[str, dict[str, Any]]:
    events: list[dict[str, Any]] = []
    text_parts: list[str] = []

    for line in stdout.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        events.append(payload)
        if payload.get("type") != "text":
            continue
        part = payload.get("part")
        if isinstance(part, dict):
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)

    if not events:
        raise PipelineError(f"Could not parse OpenCode CLI JSON response:\n{stdout}")
    return "\n".join(text_parts).strip(), {"events": events}


def gemini_extract_text(response: dict[str, Any]) -> str:
    pieces: list[str] = []
    for candidate in response.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            text = part.get("text")
            if isinstance(text, str):
                pieces.append(text)
    joined = "\n".join(pieces).strip()
    if joined:
        return joined
    if response.get("promptFeedback"):
        return json.dumps(response.get("promptFeedback"), ensure_ascii=False)
    return ""


def stringify_unknown_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
