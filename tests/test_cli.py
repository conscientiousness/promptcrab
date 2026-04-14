import os
from argparse import Namespace
from unittest.mock import patch

import pytest

from promptcrab.cli import build_config, load_environment
from promptcrab.errors import PipelineError


def make_args(**overrides: object) -> Namespace:
    base: dict[str, object] = {
        "backend": "minimax",
        "model": "MiniMax-M2.7",
        "judge_backend": None,
        "judge_model": None,
        "prompt": "hello",
        "prompt_file": None,
        "show_all": False,
        "json_output": False,
        "write_best_to": None,
        "timeout": 300,
        "max_output_tokens": None,
        "minimax_api_key": None,
        "minimax_base_url": "https://api.minimax.io/v1",
        "gemini_api_key": None,
        "gemini_executable": "gemini",
        "codex_executable": "codex",
        "codex_reasoning_effort": None,
        "judge_codex_reasoning_effort": None,
    }
    base.update(overrides)
    return Namespace(**base)


def test_build_config_leaves_max_output_tokens_unset_by_default() -> None:
    config = build_config(make_args())

    assert config.max_output_tokens is None
    assert config.judge_backend is None
    assert config.judge_model is None
    assert config.codex_reasoning_effort is None
    assert config.judge_codex_reasoning_effort is None


def test_build_config_rejects_judge_model_without_judge_backend() -> None:
    with pytest.raises(PipelineError, match="requires --judge-backend"):
        build_config(make_args(judge_model="gpt-5.4"))


def test_build_config_rejects_non_positive_max_output_tokens() -> None:
    with pytest.raises(PipelineError, match="positive integer"):
        build_config(make_args(max_output_tokens=0))


def test_load_environment_reads_dotenv_from_cwd(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("GEMINI_API_KEY=from-cwd\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with patch.dict(os.environ, {}, clear=True):
        load_environment(None)
        assert os.environ["GEMINI_API_KEY"] == "from-cwd"


def test_load_environment_explicit_file_beats_cwd_dotenv(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("GEMINI_API_KEY=from-cwd\n", encoding="utf-8")
    explicit = tmp_path / "custom.env"
    explicit.write_text("GEMINI_API_KEY=from-explicit\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with patch.dict(os.environ, {}, clear=True):
        load_environment(str(explicit))
        assert os.environ["GEMINI_API_KEY"] == "from-explicit"


def test_load_environment_does_not_override_existing_shell_env(tmp_path, monkeypatch) -> None:
    explicit = tmp_path / "custom.env"
    explicit.write_text("MINIMAX_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with patch.dict(os.environ, {"MINIMAX_API_KEY": "from-shell"}, clear=True):
        load_environment(str(explicit))
        assert os.environ["MINIMAX_API_KEY"] == "from-shell"


def test_load_environment_rejects_missing_explicit_env_file(tmp_path) -> None:
    missing = tmp_path / "missing.env"

    with pytest.raises(PipelineError, match="Could not find env file"):
        load_environment(str(missing))
