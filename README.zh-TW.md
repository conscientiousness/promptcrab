<p align="center">
  <a href="https://github.com/conscientiousness/promptcrab/actions/workflows/ci.yml"><img src="https://github.com/conscientiousness/promptcrab/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://pypi.org/project/promptcrab/"><img src="https://img.shields.io/pypi/v/promptcrab.svg?cacheSeconds=300" alt="PyPI version" /></a>
  <a href="https://pypi.org/project/promptcrab/"><img src="https://img.shields.io/badge/python-%3E%3D3.12-blue" alt="Python >=3.12" /></a>
</p>

<h1 align="center">promptcrab</h1>

<p align="center"><strong>保留原意，凝鍊成句。</strong></p>

<p align="center">
  <a href="./README.md">English</a> ·
  <a href="./README.zh-TW.md">繁體中文</a> ·
  <a href="#安裝">安裝</a> ·
  <a href="#快速開始">快速開始</a> ·
  <a href="#目前模型建議">模型建議</a>
</p>

<p align="center">
  <img src="assets/promptcrab-banner.png" alt="promptcrab pixel art banner" width="100%" />
</p>

`promptcrab` 是一個給下游 LLM 使用的 prompt rewrite CLI，重點是降低 token 成本，同時維持嚴格的 fidelity 檢查。

它不是單純把文字縮短，而是會生成多個改寫候選、檢查是否保留任務語意與順序、驗證 URL、ID、key、數字等重要 literals 是否遺失，最後只回傳最安全、最精簡的版本。

需要 Python 3.12 以上。

## 這個工具做什麼

- 生成 `zh`、`wenyan`、`en` 三個精簡候選 prompt
- 可選擇用獨立 judge backend 做驗證
- 檢查重要 literals 是否遺失
- 估算 token 數量
- 從合法候選中選出最佳結果；若都不合法，則回退原文

## 支援的 Backends

- `minimax`：使用 `MINIMAX_API_KEY` 或 `OPENAI_API_KEY`
- `gemini`：使用 `GEMINI_API_KEY`
- `gemini_cli`：使用本機 `gemini` 可執行檔與其登入狀態
- `codex_cli`：使用本機 `codex` 可執行檔

## 安裝

如果你是從本地 checkout 安裝：

```bash
uv tool install .
```

或安裝到虛擬環境：

```bash
uv pip install .
```

查看可用參數：

```bash
promptcrab --help
```

## 設定

`promptcrab` 會依照以下順序讀取憑證：

1. CLI 參數，例如 `--minimax-api-key`、`--gemini-api-key`
2. 既有 shell 環境變數
3. `--env-file /path/to/file.env`
4. 從目前工作目錄往上搜尋到的 `.env`

這樣即使用全域安裝 `promptcrab`，專案根目錄下的 `.env` 也能正常生效。

範例：

```dotenv
MINIMAX_API_KEY=your-key
GEMINI_API_KEY=your-key
OPENAI_API_KEY=your-key
```

只需要設定你實際會使用到的 backend 所需變數。

如果 provider keys 放在專案根目錄之外，可以明確指定：

```bash
promptcrab --env-file ~/.config/promptcrab/provider.env --help
```

## 快速開始

用 MiniMax 改寫 prompt：

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7 \
  --prompt "Summarize this API design and keep every field name unchanged."
```

從檔案讀 prompt：

```bash
promptcrab \
  --backend gemini \
  --model gemini-3.1-pro-preview \
  --prompt-file ./prompt.txt
```

使用固定的 judge backend，而不是 self-verification：

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7-highspeed \
  --judge-backend codex_cli \
  --judge-model gpt-5.4 \
  --prompt-file ./prompt.txt
```

用本機 Gemini CLI 改寫：

```bash
promptcrab \
  --backend gemini_cli \
  --model gemini-2.5-flash \
  --prompt-file ./prompt.txt
```

從 stdin 管線輸入：

```bash
cat ./prompt.txt | promptcrab --backend codex_cli --model gpt-5.4
```

## 常見用法

顯示所有候選與檢查結果：

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7 \
  --prompt-file ./prompt.txt \
  --show-all
```

輸出機器可讀 JSON：

```bash
promptcrab \
  --backend gemini \
  --model gemini-3.1-pro-preview \
  --prompt-file ./prompt.txt \
  --json-output
```

把最佳 prompt 寫到檔案：

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7 \
  --prompt-file ./prompt.txt \
  --write-best-to ./optimized.txt
```

若特定 provider / model 需要，可以限制 generation output：

```bash
promptcrab \
  --backend gemini \
  --model gemini-3.1-pro-preview \
  --prompt-file ./prompt.txt \
  --max-output-tokens 4096
```

指定非預設的 Codex 可執行檔：

```bash
promptcrab \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-executable /path/to/codex \
  --prompt-file ./prompt.txt
```

## 目前模型建議

目前內部 benchmark 還很小，應視為方向性參考，不是最終結論。
以下數據來自 2 組 prompt sample，並由兩個外部 judge backend 評分，token 也用同一個 tokenizer 重新計算。

| Rewrite Backend | 建議用途 | Cross-Judge Pass Rate | Consensus Pass Rate | Avg Best Token Reduction |
|---|---|---:|---:|---:|
| `codex_cli` + `gpt-5.4` | 最穩的通用 rewrite | `100.0%` | `100.0%` | `11.1%` |
| `minimax` + `MiniMax-M2.7-highspeed` | 壓縮力最強，建議搭配外部 judge | `75.0%` | `50.0%` | `18.7%` |
| `gemini_cli` + `gemini-3.1-pro-preview` | 偏實驗性，目前 cross-judge agreement 較弱 | `50.0%` | `0.0%` | `12.1%` |

建議起手式：

- 若重視 fidelity 與穩定性，使用 `codex_cli --model gpt-5.4`，必要時加上 `--codex-reasoning-effort medium|high|xhigh`，並搭配不同的 judge backend，例如 `gemini_cli` 或 `minimax`
- 若重視壓縮能力，使用 `minimax --model MiniMax-M2.7-highspeed`，並用 `codex_cli --model gpt-5.4` 當 judge
- `gemini_cli --model gemini-3.1-pro-preview` 目前較適合作為比較用 rewrite backend，不建議當預設首選

如果省略 `--judge-backend`，`promptcrab` 會跳過 judge-based verification，只保留 literal checks。速度會更快，但安全性較低。

範例：較安全的預設 rewrite

```bash
promptcrab \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-reasoning-effort medium \
  --judge-backend gemini_cli \
  --judge-model gemini-3.1-pro-preview \
  --prompt-file ./prompt.txt
```

範例：更強壓縮，搭配外部 judge

```bash
promptcrab \
  --backend minimax \
  --model MiniMax-M2.7-highspeed \
  --judge-backend codex_cli \
  --judge-model gpt-5.4 \
  --judge-codex-reasoning-effort medium \
  --prompt-file ./prompt.txt
```

對於 `codex_cli`，可以透過 `--codex-reasoning-effort` 與 `--judge-codex-reasoning-effort` 直接覆寫 reasoning effort。若省略這些參數，Codex 會回退使用本機 CLI 設定，例如 `~/.codex/config.toml`。

## 輸出模式

- 預設輸出：印出選中的最佳 prompt
- `--show-all`：印出所有候選、檢查與 verifier 結果
- `--json-output`：輸出自動化可用的 JSON
- `--write-best-to`：把選中的 prompt 寫到檔案

## 備註

- 若沒有任何候選通過 fidelity gate，`promptcrab` 會直接回傳原始 prompt
- 若有設定 `--judge-backend`，`promptcrab` 會額外跑一輪 verification 才接受候選
- 若省略 `--judge-backend`，`promptcrab` 會跳過 semantic verification，只保留 literal checks
- 若想要真正獨立的 judge，請把 `--judge-backend` 設成與 `--backend` 不同
- `promptcrab` 預設不設定 generation output cap；若特定 backend / model 需要，再傳 `--max-output-tokens`
- `--max-output-tokens` 目前只會轉發給 `minimax` 與 `gemini`；`codex_cli` 與 `gemini_cli` 在這個 wrapper 尚未對應
- token counting 依 backend 與憑證可用性而定
- 最終最佳候選不看語言，只看是否有效且 token 是否最小

## Changelog

請參考 [CHANGELOG.md](./CHANGELOG.md)。
