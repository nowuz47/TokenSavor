from scrooge.proxy import apply_optimized_prompt, extract_prompt, extract_provider_usage


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


def test_extract_provider_usage_reads_openai_current_and_legacy_shapes() -> None:
    current = {"usage": {"input_tokens": 120, "output_tokens": 40}}
    legacy = {"usage": {"prompt_tokens": 121, "completion_tokens": 41}}

    assert extract_provider_usage("openai", current) == (120, 40, "openai_usage")
    assert extract_provider_usage("openai", legacy) == (121, 41, "openai_usage")


def test_extract_provider_usage_reads_anthropic_shape() -> None:
    body = {"usage": {"input_tokens": 220, "output_tokens": 80}}

    assert extract_provider_usage("anthropic", body) == (220, 80, "anthropic_usage")


def test_extract_provider_usage_reads_gemini_usage_metadata() -> None:
    explicit = {"usageMetadata": {"promptTokenCount": 90, "candidatesTokenCount": 20}}
    total_only = {"usageMetadata": {"promptTokenCount": 90, "totalTokenCount": 115}}

    assert extract_provider_usage("gemini", explicit) == (90, 20, "gemini_usage_metadata")
    assert extract_provider_usage("gemini", total_only) == (90, 25, "gemini_usage_metadata")
