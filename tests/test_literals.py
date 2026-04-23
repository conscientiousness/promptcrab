from promptcrab.literal_checks import extract_protected_literals, literal_coverage


def test_literal_coverage_detects_missing_literals() -> None:
    original = 'Use https://example.com/api?id=42 with {"foo": 1, "bar": 2}.'
    candidate = 'Use {"foo": 1}.'

    result = literal_coverage(original, candidate)

    assert result["ok"] is False
    assert "https://example.com/api?id=42" in result["missing"]["urls"]
    assert "bar" in result["missing"]["keys"]


def test_literal_coverage_does_not_hard_gate_mixed_language_ui_terms() -> None:
    original = """比較圖: [Image #1]

1. left/right/bottom 有大量留白，要占滿整個 screen
2. 橫向 scroll list 左邊被裁切，內容 card 寬度依據比例調整
"""
    candidate = """比較圖: [Image #1]

1. 左右下方有大量留白，要占滿整個螢幕
2. 橫向滾動列表左邊被裁切，內容卡片寬度依比例調整
"""

    result = literal_coverage(original, candidate)

    assert result["ok"] is True
    assert result["protected"]["ascii_terms"] == []


def test_mixed_language_ascii_terms_are_not_hard_literals() -> None:
    original = "\n".join(
        [
            "繼續開發新策略，不是只找到一個最強的，而是能用 3-5 個策略組合達到更好效果，"
            "然後策略間 correlation 低的策略（repo 中有相關性測試代碼可以參考, "
            "kw: `finalPortfolioPrice.pct_change().dropna().corr()`）",
            "你必須了解不同換股特性 or 投資組合檔數對策略帶來影響, e.g. 月初換股, "
            "財報後換股, or 條件式換股(e.g. snow_leopard), etc.",
            "善用 subagents 搜尋論文以及網路研究，你必要找到至少三組低 correlation 策略，"
            "組合起來 sharp 至少 3.3 以上才能停下",
            "你可以使用 worktree 同步進行多個新策略開發與研究",
        ]
    )

    protected = extract_protected_literals(original)

    assert protected["ascii_terms"] == []
    assert protected["code_spans"] == ["finalPortfolioPrice.pct_change().dropna().corr()"]
    assert "kw" in protected["keys"]


def test_literal_coverage_allows_correcting_finance_sharpe_typo() -> None:
    original = """kw: `finalPortfolioPrice.pct_change().dropna().corr()`
你必要找到至少三組低 correlation 策略，組合起來 sharp 至少 3.3 以上才能停下
善用 subagents，並使用 worktree 同步進行多個新策略開發與研究"""
    candidate = """kw: `finalPortfolioPrice.pct_change().dropna().corr()`
找到至少三組低相關策略；組合 Sharpe 至少 3.3 才能停止。
善用 subagents，並使用 worktree 同步開發多個新策略。"""

    result = literal_coverage(original, candidate)

    assert result["ok"] is True
