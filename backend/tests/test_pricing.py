from scrooge.pricing import calculate_cost, get_pricing_registry
from scrooge.schemas import TokenBreakdown


def test_pricing_registry_uses_versioned_official_source() -> None:
    price = get_pricing_registry().get("anthropic", "claude-sonnet-4.6")

    assert price.version == "anthropic-2026-06-19"
    assert price.source_url.startswith("https://platform.claude.com/")


def test_cost_calculation_keeps_input_and_output_separate() -> None:
    cost = calculate_cost(
        TokenBreakdown(input_tokens=1_000_000, tokenizer="test", is_estimate=True),
        provider="openai",
        model="gpt-5.4-mini",
        expected_output_tokens=1_000_000,
    )

    assert cost.input_cost_usd == 0.75
    assert cost.output_cost_usd == 4.5
    assert cost.total_cost_usd == 5.25

