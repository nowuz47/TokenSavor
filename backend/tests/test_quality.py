from scrooge.quality import QualityCategory, evaluate_quality_report


def test_golden_prompts_preserve_required_terms() -> None:
    report = evaluate_quality_report()

    assert report.total_cases >= 50
    assert report.passed_cases == report.total_cases
    assert report.harmful_omission_count == 0
    assert report.hallucinated_constraint_count == 0


def test_short_structured_prompts_may_report_zero_savings_without_failing_quality() -> None:
    report = evaluate_quality_report()
    zero_or_low_savings = [result for result in report.results if result.savings_rate < 0.2]

    assert zero_or_low_savings
    assert all(result.passed for result in zero_or_low_savings)
    assert report.over_optimization_count == 0


def test_each_quality_category_has_mvp_minimum_cases_and_passes_floor() -> None:
    report = evaluate_quality_report()
    by_category = {item.category: item for item in report.category_summaries}

    assert set(by_category) == set(QualityCategory)
    for summary in by_category.values():
        assert summary.total_cases >= 10
        assert summary.passed_cases == summary.total_cases
        assert summary.preservation_pass_rate >= 0.95
        assert summary.savings_floor_failures == 0


def test_repetitive_context_categories_produce_meaningful_savings() -> None:
    report = evaluate_quality_report()
    by_name = {result.name: result for result in report.results}

    assert by_name["logs_long_payment"].savings_rate >= 0.2
    assert by_name["logs_frequency_summary"].savings_rate >= 0.2
    assert by_name["coding_large_diff"].savings_rate >= 0.2
