from promptcrab.parsing import (
    extract_gemini_cli_result,
    extract_opencode_result,
    parse_json_response,
)


def test_parse_json_response_accepts_fenced_json() -> None:
    payload = """```json
    {"faithful": true}
    ```"""

    result = parse_json_response(payload)

    assert result == {"faithful": True}


def test_extract_gemini_cli_result_reads_json_response() -> None:
    stdout = """{
      "session_id": "abc",
      "response": "rewritten",
      "stats": {"models": {}}
    }"""

    response, payload = extract_gemini_cli_result(stdout)

    assert response == "rewritten"
    assert payload["session_id"] == "abc"


def test_extract_opencode_result_reads_jsonl_events() -> None:
    stdout = "\n".join(
        [
            '{"type":"step_start","sessionID":"abc"}',
            '{"type":"text","part":{"text":"rewritten"}}',
            '{"type":"step_finish","sessionID":"abc"}',
        ]
    )

    response, payload = extract_opencode_result(stdout)

    assert response == "rewritten"
    assert len(payload["events"]) == 3
