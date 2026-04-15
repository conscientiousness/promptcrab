from typing import Any

import pytest

from promptcrab.backends import (
    CodexCLIBackend,
    GeminiBackend,
    GeminiCLIBackend,
    MiniMaxBackend,
    OpenCodeCLIBackend,
)
from promptcrab.errors import PipelineError


def test_minimax_generate_omits_max_completion_tokens_by_default(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_http_post_json(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {"choices": [{"message": {"content": "rewritten"}}], "usage": {}}

    monkeypatch.setattr("promptcrab.backends.http_post_json", fake_http_post_json)
    backend = MiniMaxBackend(model="MiniMax-M2.7", api_key="test-key")

    text, meta = backend.generate(system_prompt="system", user_prompt="user")

    assert text == "rewritten"
    assert meta["usage"] == {}
    assert "max_completion_tokens" not in captured["payload"]


def test_minimax_generate_passes_max_completion_tokens_when_requested(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_http_post_json(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "rewritten"}}], "usage": {}}

    monkeypatch.setattr("promptcrab.backends.http_post_json", fake_http_post_json)
    backend = MiniMaxBackend(model="MiniMax-M2.7", api_key="test-key")

    backend.generate(
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=4096,
    )

    assert captured["payload"]["max_completion_tokens"] == 4096


def test_gemini_generate_omits_max_output_tokens_by_default(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_http_post_json(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        captured["payload"] = payload
        return {"candidates": [{"content": {"parts": [{"text": "rewritten"}]}}]}

    monkeypatch.setattr("promptcrab.backends.http_post_json", fake_http_post_json)
    backend = GeminiBackend(model="gemini-2.5-pro", api_key="test-key")

    text, _meta = backend.generate(system_prompt="system", user_prompt="user")

    assert text == "rewritten"
    assert "maxOutputTokens" not in captured["payload"]["generationConfig"]


def test_gemini_generate_passes_max_output_tokens_when_requested(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_http_post_json(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        captured["payload"] = payload
        return {"candidates": [{"content": {"parts": [{"text": "rewritten"}]}}]}

    monkeypatch.setattr("promptcrab.backends.http_post_json", fake_http_post_json)
    backend = GeminiBackend(model="gemini-2.5-pro", api_key="test-key")

    backend.generate(
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=8192,
    )

    assert captured["payload"]["generationConfig"]["maxOutputTokens"] == 8192


def test_gemini_cli_generate_parses_headless_json(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_subprocess(
        cmd: list[str],
        input_text: str | None,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        captured["cmd"] = cmd
        captured["input_text"] = input_text
        captured["timeout"] = timeout
        captured["env"] = env
        return '{"session_id":"abc","response":"rewritten","stats":{"models":{}}}', ""

    monkeypatch.setattr("promptcrab.backends.shutil.which", lambda executable: "/usr/bin/gemini")
    monkeypatch.setattr("promptcrab.backends.run_subprocess", fake_run_subprocess)
    backend = GeminiCLIBackend(model="gemini-2.5-flash", executable="gemini")

    text, meta = backend.generate(system_prompt="system", user_prompt="user")

    assert text == "rewritten"
    assert meta["stats"] == {"models": {}}
    assert captured["cmd"][:4] == ["gemini", "-m", "gemini-2.5-flash", "-p"]
    assert captured["env"] is None


def test_gemini_cli_rejects_max_output_tokens(monkeypatch) -> None:
    monkeypatch.setattr("promptcrab.backends.shutil.which", lambda executable: "/usr/bin/gemini")
    backend = GeminiCLIBackend(model="gemini-2.5-flash", executable="gemini")

    with pytest.raises(PipelineError, match="not supported for gemini_cli"):
        backend.generate(
            system_prompt="system",
            user_prompt="user",
            max_output_tokens=1024,
        )


def test_codex_generate_rejects_max_output_tokens(monkeypatch) -> None:
    monkeypatch.setattr("promptcrab.backends.shutil.which", lambda executable: "/usr/bin/codex")
    backend = CodexCLIBackend(model="gpt-5.4", executable="codex")

    with pytest.raises(PipelineError, match="not supported for codex_cli"):
        backend.generate(
            system_prompt="system",
            user_prompt="user",
            max_output_tokens=1024,
        )


def test_codex_generate_uses_current_cli_flags(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_subprocess(
        cmd: list[str],
        input_text: str | None,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        captured["cmd"] = cmd
        captured["input_text"] = input_text
        captured["timeout"] = timeout
        captured["env"] = env
        return "rewritten", ""

    monkeypatch.setattr("promptcrab.backends.shutil.which", lambda executable: "/usr/bin/codex")
    monkeypatch.setattr("promptcrab.backends.run_subprocess", fake_run_subprocess)
    backend = CodexCLIBackend(model="gpt-5.4", executable="codex")

    text, _meta = backend.generate(system_prompt="system", user_prompt="user")

    assert text == "rewritten"
    assert "--ask-for-approval" not in captured["cmd"]


def test_codex_generate_passes_reasoning_effort_override(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_subprocess(
        cmd: list[str],
        input_text: str | None,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        captured["cmd"] = cmd
        return "rewritten", ""

    monkeypatch.setattr("promptcrab.backends.shutil.which", lambda executable: "/usr/bin/codex")
    monkeypatch.setattr("promptcrab.backends.run_subprocess", fake_run_subprocess)
    backend = CodexCLIBackend(
        model="gpt-5.4",
        executable="codex",
        reasoning_effort="medium",
    )

    text, _meta = backend.generate(system_prompt="system", user_prompt="user")

    assert text == "rewritten"
    assert "-c" in captured["cmd"]
    assert 'model_reasoning_effort="medium"' in captured["cmd"]


def test_opencode_generate_parses_json_events(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_subprocess(
        cmd: list[str],
        input_text: str | None,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        captured["cmd"] = cmd
        captured["input_text"] = input_text
        return (
            '{"type":"step_start"}\n'
            '{"type":"text","part":{"text":"rewritten"}}\n'
            '{"type":"step_finish"}',
            "",
        )

    monkeypatch.setattr("promptcrab.backends.shutil.which", lambda executable: "/usr/bin/opencode")
    monkeypatch.setattr("promptcrab.backends.run_subprocess", fake_run_subprocess)
    backend = OpenCodeCLIBackend(
        model="minimax-coding-plan/MiniMax-M2.7-highspeed",
        executable="opencode",
    )

    text, meta = backend.generate(system_prompt="system", user_prompt="user")

    assert text == "rewritten"
    assert meta["raw"]["events"][1]["type"] == "text"
    assert captured["cmd"][:5] == [
        "opencode",
        "run",
        "-m",
        "minimax-coding-plan/MiniMax-M2.7-highspeed",
        "--format",
    ]
    assert captured["input_text"] is None
