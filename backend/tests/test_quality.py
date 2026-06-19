from scrooge.quality import evaluate_golden_suite


def test_golden_prompts_preserve_required_terms() -> None:
    results = evaluate_golden_suite()

    assert results
    assert all(result.passed for result in results)


def test_short_structured_prompts_may_report_zero_savings_without_failing_quality() -> None:
    results = evaluate_golden_suite()
    zero_or_low_savings = [result for result in results if result.savings_rate < 0.2]

    assert zero_or_low_savings
    assert all(result.passed for result in zero_or_low_savings)
