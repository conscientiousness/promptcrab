# Maintainers

這份文件只給專案維護者看，放在 `.github/` 下，不會進入目前的套件分發內容。

## Local Maintenance

```bash
uv sync --dev
uv run ruff check .
uv run pyright
uv run pytest
```

最低支援 Python 版本：`3.12`

完整 release baseline：

```bash
./scripts/release_check.sh
```

版本試算：

```bash
uv run python scripts/bump_calver.py --dry-run
uv run python scripts/bump_calver.py --kind beta --dry-run
```

## Versioning

版本格式與 `crabyard` 一致，使用 CalVer：

```text
YYYY.M.D
YYYY.M.D-1
YYYY.M.D-beta.1
```

單一版本來源：

- `src/promptcrab/__about__.py`
- `CHANGELOG.md` 的 release section

版本工具：

- `scripts/bump_calver.py`: 自動 bump CalVer，並把 `CHANGELOG.md` 的 `Unreleased` 切成正式 release section
- `scripts/render_release_notes.py`: 從 `CHANGELOG.md` 擷取指定版本的 release notes

`CHANGELOG.md` 維護方式：

1. 平常把使用者可見變更寫在 `## Unreleased` 下。
2. 發版前執行 `uv run python scripts/bump_calver.py`。
3. 工具會更新 `src/promptcrab/__about__.py`，並把 `Unreleased` 切成新的版本段落。

## CI

`/.github/workflows/ci.yml` 會執行：

- Python `3.12` 與 `3.13`
- `uv sync --dev --frozen`
- `ruff`
- `pyright`
- `pytest`
- `uv build`
- `twine check dist/*`
- 以 built wheel 做 CLI smoke test

## Release

`/.github/workflows/release-prepare.yml` 只在推送 `v*` tag 時執行。

release workflow 目前使用 Python `3.12`。

發布流程：

1. 修改 `src/promptcrab/__about__.py` 的版本號。
2. 確認 `CHANGELOG.md` 的 `## Unreleased` 已整理好。
3. 執行 `uv run python scripts/bump_calver.py`。
4. 執行 `./scripts/release_check.sh`。
5. 提交版本變更。
6. 在 `main` 當前 HEAD 上建立對應 tag，例如 `v2026.4.14`。
7. 推送 `main` 與 tag。

workflow 會驗證：

- tag 必須符合 `vYYYY.M.D[-suffix]`
- tag 必須指向 `origin/main` 的當前 HEAD
- tag 版本必須與 `src/promptcrab/__about__.py` 一致

通過後會：

- 發布到 PyPI
- 依照 `CHANGELOG.md` 建立 GitHub Release notes
- 建立 GitHub Release

## PyPI

第一次正式發布前，要先在 PyPI 設定這個 repo 的 trusted publishing（GitHub OIDC）。
