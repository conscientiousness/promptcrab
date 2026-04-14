from promptcrab.prompts import build_rewrite_user_prompt, build_verifier_user_prompt


def test_rewrite_prompt_mentions_mixed_language_ui_terms() -> None:
    prompt = build_rewrite_user_prompt("sample", "zh")

    assert "[Image #1]" in prompt
    assert "left/right/bottom" in prompt
    assert "scroll list" in prompt
    assert "do not turn a user question into an" in prompt
    assert "query inspectors, state dumps" in prompt


def test_verifier_prompt_mentions_translation_risk_for_ui_terms() -> None:
    prompt = build_verifier_user_prompt("orig", "candidate")

    assert "translated or normalized technical/UI terms" in prompt
    assert "[Image #1]" in prompt
    assert "left/right/bottom" in prompt
    assert "same interaction mode and response expectation" in prompt
    assert "structured diagnostic blocks" in prompt
