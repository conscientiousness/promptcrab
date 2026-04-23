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

`promptcrab` 是一個給下游 LLM 使用的 prompt rewrite CLI，重點是先提升 prompt 品質、修正一般語句問題與結構，再降低 token 成本，同時維持嚴格的 fidelity 檢查。

它不是單純把文字縮短，而是會先產生一份同語言的 `canonical` 改寫，讓 prompt 更清楚、更容易被另一個 LLM 正確執行。接著再從這份更乾淨的來源產生翻譯/精簡候選，並且仍以原始 prompt 做驗證、檢查 URL、ID、key、數字等重要 literals 是否遺失，最後只回傳最安全且夠精簡的版本。

需要 Python 3.12 以上。

## 這個工具做什麼

- 先把原始 prompt 改寫成一份更清楚的同語言 `canonical` 候選
- 再從 canonical 來源產生 `zh`、`wenyan`、`en` 三個更清楚、可執行性更高的候選 prompt
- 可選擇用獨立 judge backend 做驗證
- 檢查重要 literals 是否遺失
- 估算 token 數量
- 從合法候選中選出最佳結果，先看 fidelity 與清楚度，再看 token 節省；若都不合法，則回退原文

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

透過 opencode 使用 MiniMax 改寫 prompt：

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --prompt "Summarize this API design and keep every field name unchanged."
```

用本機 Gemini CLI 從檔案讀 prompt：

```bash
promptcrab \
  --backend gemini_cli \
  --model gemini-3-flash-preview \
  --prompt-file ./prompt.txt
```

使用固定的 judge backend，而不是 self-verification：

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --judge-backend codex_cli \
  --judge-model gpt-5.4 \
  --judge-codex-reasoning-effort medium \
  --prompt-file ./prompt.txt
```

用本機 Gemini CLI 改寫：

```bash
promptcrab \
  --backend gemini_cli \
  --model gemini-3-flash-preview \
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
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --prompt-file ./prompt.txt \
  --show-all
```

輸出機器可讀 JSON：

```bash
promptcrab \
  --backend gemini_cli \
  --model gemini-3-flash-preview \
  --prompt-file ./prompt.txt \
  --json-output
```

使用固定本地 tokenizer，取得更快且可重現的 token 計數：

```bash
promptcrab \
  --backend codex_cli \
  --model gpt-5.4 \
  --prompt-file ./prompt.txt \
  --tokenizer o200k_base
```

把最佳 prompt 寫到檔案：

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
  --prompt-file ./prompt.txt \
  --write-best-to ./optimized.txt
```

若特定 provider / model 需要，可以限制 generation output：

```bash
promptcrab \
  --backend gemini \
  --model gemini-3-flash-preview \
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

與其在 README 內維護容易過時的小樣本靜態表格，現在建議直接用 `promptcrab-benchmark` 重跑 benchmark。它會跑內建 literal / format hard-case suite、抓公開網路資料集、使用共享 tokenizer 重新計 token，並用多個外部 judge 做 panel 評估。

### 方向性快照

這個單 judge 快照在 2026-04-15 跑出，目標是提供一個能快速完成、適合放在 README 的比較表。設定是 MT-Bench 抽 4 題、IFEval 抽 4 題，合計 8 題；共享 tokenizer 使用 `o200k_base`；保留 literal checks；所有列都用 `codex_cli + gpt-5.4 (medium)` 當 judge。請把它視為方向性參考，不是最終排名；其中 GPT 列是 self-judged。

`通過案例平均 token reduction` 只計算至少有一個候選通過 fidelity gates 的案例。

| Rewrite backend | Judge | Sample | Pass rate (95% CI) | 通過案例平均 token reduction (95% CI) | Dataset pass split | 備註 |
|---|---|---:|---:|---:|---|---|
| `codex_cli + gpt-5.4 (medium)` | `codex_cli + gpt-5.4 (medium)` | `8` | `6/8 = 75.0%` (`40.9-92.9%`) | `4.8%` (`-5.5-12.3%`) | MT-Bench `4/4`, IFEval `2/4` | Self-judged；壓縮最保守。IFEval 失敗主因是嚴格 literal / verbatim 約束。 |
| `opencode_cli + MiniMax-M2.7-highspeed` | `codex_cli + gpt-5.4 (medium)` | `8` | `2/8 = 25.0%` (`7.1-59.1%`) | `20.1%` (`19.2-20.9%`) | MT-Bench `2/4`, IFEval `0/4` | 通過案例壓縮最多，但多個 IFEval case 因 literal 或格式漂移失敗。 |
| `gemini_cli + gemini-3-flash-preview` | `codex_cli + gpt-5.4 (medium)` | `8` | `4/8 = 50.0%` (`21.5-78.5%`) | `7.8%` (`-16.7-26.3%`) | MT-Bench `3/4`, IFEval `1/4` | fidelity 居中；失敗多來自翻譯或刪減 literal constraints。 |

內建案例來源：

- `hard_cases`：內建 literal 與格式保留測資，涵蓋逐字重複、bullet template、精確 marker、段落 separator、大小寫 / 數量約束、符號、JSON keys 與 URL
- [MT-Bench](https://raw.githubusercontent.com/lm-sys/FastChat/main/fastchat/llm_judge/data/mt_bench/question.jsonl)
- [IFEval](https://raw.githubusercontent.com/google-research/google-research/master/instruction_following_eval/data/input_data.jsonl)

這個 benchmark 會提供：

- 每個 judge 的 pass rate 與 95% Wilson confidence interval
- 多 judge 共識 pass rate
- gate 前 token reduction，用來看最短 raw candidate 在 fidelity 檢查前壓縮多少
- gate 後 token reduction，用來看通過 literal 與 judge gates 後的可接受壓縮量
- 平均 token reduction 的 95% bootstrap confidence interval
- judge 兩兩 agreement 與 Cohen's kappa
- 分資料集拆解結果

範例：用 hard cases 與公開真實案例重跑 benchmark

```bash
promptcrab-benchmark \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-reasoning-effort medium \
  --judge gemini_cli:gemini-3-flash-preview \
  --judge opencode_cli:minimax-coding-plan/MiniMax-M2.7-highspeed \
  --dataset hard_cases \
  --dataset mt_bench \
  --dataset ifeval \
  --cases-per-dataset 24 \
  --trials 2 \
  --tokenizer o200k_base
```

如果你想跑完整資料集，而不是抽樣：

```bash
promptcrab-benchmark \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-reasoning-effort medium \
  --judge gemini_cli:gemini-3-flash-preview \
  --judge opencode_cli:minimax-coding-plan/MiniMax-M2.7-highspeed \
  --dataset hard_cases \
  --dataset mt_bench \
  --dataset ifeval \
  --cases-per-dataset 0 \
  --tokenizer o200k_base
```

選取 `hard_cases` 時會固定跑完整內建 suite；`--cases-per-dataset` 只限制外部資料集抽樣數。

建議起手式：

- 若重視 fidelity 與穩定性，使用 `codex_cli --model gpt-5.4`，必要時加上 `--codex-reasoning-effort medium|high|xhigh`，並搭配不同的 judge backend，例如 `gemini_cli` 或 `opencode_cli`
- 若重視壓縮能力，可以比較 `opencode_cli --model minimax-coding-plan/MiniMax-M2.7-highspeed`，並用 `codex_cli --model gpt-5.4` 當 judge
- `gemini_cli --model gemini-3-flash-preview` 目前較適合作為比較用 rewrite backend；在上方方向性快照中，literal fidelity 弱於 `gpt-5.4`

如果省略 `--judge-backend`，`promptcrab` 會跳過 judge-based verification，只保留 literal checks。速度會更快，但安全性較低。

範例：較安全的預設 rewrite

```bash
promptcrab \
  --backend codex_cli \
  --model gpt-5.4 \
  --codex-reasoning-effort medium \
  --judge-backend gemini_cli \
  --judge-model gemini-3-flash-preview \
  --prompt-file ./prompt.txt
```

範例：更強壓縮，搭配外部 judge

```bash
promptcrab \
  --backend opencode_cli \
  --model minimax-coding-plan/MiniMax-M2.7-highspeed \
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
- 正常模式下，`promptcrab` 會先產生 `canonical` 候選，再從它產生翻譯候選；翻譯候選不會暗中切回原始 prompt 當來源
- `wenyan` 候選必須是嚴格文言文，不允許在 `wenyan` 標籤下回傳現代中文
- 若有設定 `--judge-backend`，`promptcrab` 會並行生成翻譯語言候選，跳過 literal 已失敗的候選 judge，並優先 judge token 最省的候選，再視需要擴大到其餘候選
- 若省略 `--judge-backend`，`promptcrab` 會跳過 semantic verification，只保留 literal checks
- 若想要真正獨立的 judge，請把 `--judge-backend` 設成與 `--backend` 不同
- `promptcrab` 預設不設定 generation output cap；若特定 backend / model 需要，再傳 `--max-output-tokens`
- `--max-output-tokens` 目前只會轉發給 `minimax` 與 `gemini`；`codex_cli` 與 `gemini_cli` 在這個 wrapper 尚未對應
- `promptcrab` 現在預設使用 `--tokenizer o200k_base` 的共享本地 tokenizer，避免 backend/API token counting fallback，速度較快且結果較穩定
- 若你需要舊的 backend-native token counting 路徑，請改傳 `--tokenizer backend`
- 最終最佳候選不看語言，只看是否有效且 token 是否最小

## Changelog

請參考 [CHANGELOG.md](./CHANGELOG.md)。
