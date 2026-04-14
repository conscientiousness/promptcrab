#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

rm -rf dist

uv sync --dev --frozen
uv run ruff check .
uv run pyright
uv run pytest
uv build
uv run twine check dist/*

WHEEL_PATH="$(ls dist/*.whl)"
uv tool run --from "$WHEEL_PATH" promptcrab --help >/dev/null
