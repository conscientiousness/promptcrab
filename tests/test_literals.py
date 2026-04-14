from promptcrab.literal_checks import literal_coverage


def test_literal_coverage_detects_missing_literals() -> None:
    original = 'Use https://example.com/api?id=42 with {"foo": 1, "bar": 2}.'
    candidate = 'Use {"foo": 1}.'

    result = literal_coverage(original, candidate)

    assert result["ok"] is False
    assert "https://example.com/api?id=42" in result["missing"]["urls"]
    assert "bar" in result["missing"]["keys"]


def test_literal_coverage_detects_missing_mixed_language_ui_terms() -> None:
    original = """比較圖: [Image #1]

1. left/right/bottom 有大量留白，要占滿整個 screen
2. 橫向 scroll list 左邊被裁切，內容 card 寬度依據比例調整
"""
    candidate = """比較圖: [Image #1]

1. 左右下方有大量留白，要占滿整個螢幕
2. 橫向滾動列表左邊被裁切，內容卡片寬度依比例調整
"""

    result = literal_coverage(original, candidate)

    assert result["ok"] is False
    assert "left/right/bottom" in result["missing"]["ascii_terms"]
    assert "screen" in result["missing"]["ascii_terms"]
    assert "scroll list" in result["missing"]["ascii_terms"]
    assert "card" in result["missing"]["ascii_terms"]
