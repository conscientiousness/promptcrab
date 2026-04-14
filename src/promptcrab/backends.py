from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from promptcrab.errors import PipelineError
from promptcrab.models import PipelineConfig
from promptcrab.parsing import (
    extract_gemini_cli_result,
    gemini_extract_text,
    stringify_unknown_content,
)
from promptcrab.prompts import combine_system_user


class BaseBackend(ABC):
    name = "base"

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        timeout: int = 300,
    ) -> tuple[str, dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def count_text_tokens(self, text: str, timeout: int = 120) -> tuple[int, str]:
        raise NotImplementedError


class MiniMaxBackend(BaseBackend):
    name = "minimax"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str = "https://api.minimax.io/v1",
    ) -> None:
        super().__init__(model=model)
        self.api_key = (
            api_key or os.environ.get("MINIMAX_API_KEY") or os.environ.get("OPENAI_API_KEY")
        )
        self.base_url = base_url.rstrip("/")
        self._count_overhead: int | None = None
        if not self.api_key:
            raise PipelineError("MiniMax backend needs MINIMAX_API_KEY or OPENAI_API_KEY.")

    def _chat_completion(
        self,
        messages: list[dict[str, str]],
        timeout: int = 300,
        max_completion_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "reasoning_split": True,
        }
        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens
        return http_post_json(
            url=f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload=payload,
            timeout=timeout,
        )

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        timeout: int = 300,
    ) -> tuple[str, dict[str, Any]]:
        schema_hint = ""
        if json_schema is not None:
            schema_hint = (
                "\n\nReturn JSON only. The response must conform to this JSON Schema:\n"
                + json.dumps(json_schema, ensure_ascii=False)
            )
        response = self._chat_completion(
            messages=[
                {"role": "system", "content": system_prompt + schema_hint},
                {"role": "user", "content": user_prompt},
            ],
            timeout=timeout,
            max_completion_tokens=max_output_tokens,
        )
        message = (response.get("choices") or [{}])[0].get("message") or {}
        text = message.get("content", "")
        if not isinstance(text, str):
            text = stringify_unknown_content(text)
        return text.strip(), {"raw": response, "usage": response.get("usage", {})}

    def _wrapper_prompt_tokens(self, text: str, timeout: int = 120) -> int:
        response = self._chat_completion(
            messages=[
                {"role": "system", "content": "Read the user's message. Reply with exactly: OK"},
                {"role": "user", "content": text},
            ],
            timeout=timeout,
            max_completion_tokens=1,
        )
        usage = response.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        if not isinstance(prompt_tokens, int):
            raise PipelineError(f"MiniMax did not return prompt_tokens in usage: {usage}")
        return prompt_tokens

    def count_text_tokens(self, text: str, timeout: int = 120) -> tuple[int, str]:
        if self._count_overhead is None:
            self._count_overhead = self._wrapper_prompt_tokens("", timeout=timeout)
        counted = self._wrapper_prompt_tokens(text, timeout=timeout)
        return max(0, counted - self._count_overhead), "minimax_usage_wrapper_normalized"


class GeminiBackend(BaseBackend):
    name = "gemini"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        super().__init__(model=model)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise PipelineError("Gemini backend needs GEMINI_API_KEY.")

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        timeout: int = 300,
    ) -> tuple[str, dict[str, Any]]:
        body: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0},
        }
        if json_schema is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = json_schema
        if max_output_tokens is not None:
            body["generationConfig"]["maxOutputTokens"] = max_output_tokens
        response = http_post_json(
            url=(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self.api_key}"
            ),
            headers={},
            payload=body,
            timeout=timeout,
        )
        text = gemini_extract_text(response)
        return text.strip(), {"raw": response, "usage": response.get("usageMetadata", {})}

    def count_text_tokens(self, text: str, timeout: int = 120) -> tuple[int, str]:
        body = {"contents": [{"role": "user", "parts": [{"text": text}]}]}
        response = http_post_json(
            url=(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:countTokens?key={self.api_key}"
            ),
            headers={},
            payload=body,
            timeout=timeout,
        )
        total = response.get("totalTokens")
        if not isinstance(total, int):
            raise PipelineError(f"Gemini countTokens did not return totalTokens: {response}")
        return total, "gemini_countTokens"


class GeminiCLIBackend(BaseBackend):
    name = "gemini_cli"

    def __init__(
        self,
        model: str,
        executable: str = "gemini",
        api_key: str | None = None,
    ) -> None:
        super().__init__(model=model)
        self.executable = executable
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if shutil.which(self.executable) is None:
            raise PipelineError(f"Could not find {self.executable!r} in PATH.")

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        timeout: int = 300,
    ) -> tuple[str, dict[str, Any]]:
        if max_output_tokens is not None:
            raise PipelineError("--max-output-tokens is not supported for gemini_cli.")
        final_prompt = combine_system_user(system_prompt, user_prompt)
        command = [
            self.executable,
            "-m",
            self.model,
            "-p",
            final_prompt,
            "-o",
            "json",
            "--approval-mode",
            "plan",
        ]
        stdout, stderr = run_subprocess(command, input_text=None, timeout=timeout)
        text, payload = extract_gemini_cli_result(stdout)
        return text.strip(), {
            "raw": payload,
            "stats": payload.get("stats", {}),
            "stderr": stderr,
            "command": command,
        }

    def count_text_tokens(self, text: str, timeout: int = 120) -> tuple[int, str]:
        if self.api_key:
            backend = GeminiBackend(model=self.model, api_key=self.api_key)
            return backend.count_text_tokens(text, timeout=timeout)
        return len(text), "character_count_fallback"


class CodexCLIBackend(BaseBackend):
    name = "codex_cli"

    def __init__(
        self,
        model: str,
        executable: str = "codex",
        reasoning_effort: str | None = None,
    ) -> None:
        super().__init__(model=model)
        self.executable = executable
        self.reasoning_effort = reasoning_effort
        if shutil.which(self.executable) is None:
            raise PipelineError(f"Could not find {self.executable!r} in PATH.")

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        timeout: int = 300,
    ) -> tuple[str, dict[str, Any]]:
        if max_output_tokens is not None:
            raise PipelineError("--max-output-tokens is not supported for codex_cli.")
        final_prompt = combine_system_user(system_prompt, user_prompt)
        with tempfile.TemporaryDirectory(prefix="codex-rewrite-") as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "final.txt"
            command = [
                self.executable,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--model",
                self.model,
                "--output-last-message",
                str(output_path),
            ]
            if self.reasoning_effort is not None:
                command.extend(["-c", f'model_reasoning_effort="{self.reasoning_effort}"'])
            if json_schema is not None:
                schema_path = temp_path / "schema.json"
                schema_path.write_text(
                    json.dumps(json_schema, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                command.extend(["--output-schema", str(schema_path)])
            command.append("-")
            stdout, stderr = run_subprocess(command, input_text=final_prompt, timeout=timeout)
            if output_path.exists():
                text = output_path.read_text(encoding="utf-8").strip()
            else:
                text = stdout.strip()
            return text, {
                "stdout": stdout,
                "stderr": stderr,
                "command": command,
            }

    def count_text_tokens(self, text: str, timeout: int = 120) -> tuple[int, str]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return openai_count_tokens(
                model=self.model,
                text=text,
                api_key=api_key,
                timeout=timeout,
            ), "openai_input_tokens_api"
        fallback = maybe_tiktoken_count(self.model, text)
        if fallback is not None:
            return fallback, "tiktoken_fallback"
        return len(text), "character_count_fallback"


def build_backend(config: PipelineConfig) -> BaseBackend:
    if config.backend == "minimax":
        return MiniMaxBackend(
            model=config.model,
            api_key=config.minimax_api_key,
            base_url=config.minimax_base_url,
        )
    if config.backend == "gemini":
        return GeminiBackend(model=config.model, api_key=config.gemini_api_key)
    if config.backend == "gemini_cli":
        return GeminiCLIBackend(
            model=config.model,
            executable=config.gemini_executable,
            api_key=config.gemini_api_key,
        )
    return CodexCLIBackend(
        model=config.model,
        executable=config.codex_executable,
        reasoning_effort=config.codex_reasoning_effort,
    )


def http_post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise PipelineError(f"HTTP {exc.code} calling {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise PipelineError(f"Network error calling {url}: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Non-JSON response from {url}: {body[:800]}") from exc


def run_subprocess(
    cmd: list[str],
    input_text: str | None,
    timeout: int,
    env: dict[str, str] | None = None,
) -> tuple[str, str]:
    try:
        process = subprocess.run(
            cmd,
            input=input_text.encode("utf-8") if input_text is not None else None,
            capture_output=True,
            env={**os.environ, **env} if env is not None else None,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PipelineError(f"Executable not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(f"Command timed out after {timeout}s: {' '.join(cmd)}") from exc

    stdout = process.stdout.decode("utf-8", errors="replace")
    stderr = process.stderr.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise PipelineError(
            f"Command failed ({process.returncode}): {' '.join(cmd)}\n"
            f"STDERR:\n{stderr}\n"
            f"STDOUT:\n{stdout}"
        )
    return stdout, stderr


def maybe_tiktoken_count(model: str, text: str) -> int | None:
    try:
        import tiktoken
    except Exception:
        return None

    candidate_models = [model]
    if "/" in model:
        candidate_models.append(model.split("/", 1)[1])

    encoding = None
    for model_name in candidate_models:
        try:
            encoding = tiktoken.encoding_for_model(model_name)
            break
        except Exception:
            continue

    if encoding is None:
        for name in ("o200k_base", "cl100k_base"):
            try:
                encoding = tiktoken.get_encoding(name)
                break
            except Exception:
                continue
    if encoding is None:
        return None
    return len(encoding.encode(text))


def openai_count_tokens(model: str, text: str, api_key: str, timeout: int = 120) -> int:
    response = http_post_json(
        url="https://api.openai.com/v1/responses/input_tokens",
        headers={"Authorization": f"Bearer {api_key}"},
        payload={"model": model, "input": text},
        timeout=timeout,
    )
    count = response.get("input_tokens")
    if not isinstance(count, int):
        raise PipelineError(f"OpenAI input token count response missing input_tokens: {response}")
    return count
