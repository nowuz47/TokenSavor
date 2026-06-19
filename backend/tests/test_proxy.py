from scrooge.proxy import apply_optimized_prompt, extract_prompt


def test_proxy_rewrites_prompt_payload_for_forwarding() -> None:
    payload = {"model": "gpt-5.4-mini", "prompt": "please check this long repeated prompt"}

    updated, changed = apply_optimized_prompt(payload, "Goal: check the prompt")

    assert changed is True
    assert updated["prompt"] == "Goal: check the prompt"
    assert payload["prompt"] == "please check this long repeated prompt"


def test_proxy_rewrites_last_user_message() -> None:
    payload = {
        "model": "gpt-5.4-mini",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Investigate this stack trace"},
        ],
    }

    updated, changed = apply_optimized_prompt(payload, "Goal: investigate stack trace")

    assert changed is True
    assert updated["messages"][0]["content"] == "Be concise."
    assert updated["messages"][1]["content"] == "Goal: investigate stack trace"


def test_extract_prompt_reads_content_blocks() -> None:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Build a calculator"},
                    {"type": "text", "text": "No eval allowed"},
                ],
            }
        ]
    }

    assert extract_prompt(payload) == "Build a calculator\nNo eval allowed"
