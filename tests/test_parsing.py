from promptcrab.parsing import extract_gemini_cli_result, parse_json_response


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
