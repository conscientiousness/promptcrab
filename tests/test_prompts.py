from promptcrab.prompts import build_rewrite_user_prompt, build_verifier_user_prompt


def test_rewrite_prompt_mentions_mixed_language_ui_terms() -> None:
    prompt = build_rewrite_user_prompt("sample", "zh")

    assert "improve prompt effectiveness" in prompt
    assert "fix obvious prose-level typos" in prompt
    assert "reduce tokens only after clarity" in prompt
    assert "preserve intentional misspellings" in prompt
    assert "[Image #1]" in prompt
    assert "left/right/bottom" in prompt
    assert "scroll list" in prompt
    assert "do not turn a user question into an" in prompt
    assert "query inspectors, state dumps" in prompt


def test_canonical_rewrite_prompt_uses_original_language_without_translation() -> None:
    prompt = build_rewrite_user_prompt("sample", "canonical")

    assert "the original language only" in prompt
    assert "Do not translate" in prompt
    assert "canonical quality rewrite" in prompt


def test_wenyan_prompt_disallows_modern_chinese_fallback() -> None:
    prompt = build_rewrite_user_prompt("sample", "wenyan")

    assert "Classical Chinese (Wenyan)" in prompt
    assert "do not fall back to modern Chinese" in prompt
    assert "otherwise use very terse modern Chinese" not in prompt


def test_verifier_prompt_mentions_translation_risk_for_ui_terms() -> None:
    prompt = build_verifier_user_prompt("orig", "candidate")

    assert "translated or normalized technical/UI terms" in prompt
    assert "at least as clear and actionable" in prompt
    assert "typo or sentence" in prompt
    assert "[Image #1]" in prompt
    assert "left/right/bottom" in prompt
    assert "same interaction mode and response expectation" in prompt
    assert "structured diagnostic blocks" in prompt
