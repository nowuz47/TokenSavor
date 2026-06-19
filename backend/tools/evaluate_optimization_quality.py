from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrooge.quality import evaluate_quality_report  # noqa: E402


def main() -> int:
    report = evaluate_quality_report()
    payload = {
        "passed": report.passed_cases,
        "total": report.total_cases,
        "quality_preservation_rate": report.quality_preservation_rate,
        "average_savings_rate": report.average_savings_rate,
        "harmful_omission_count": report.harmful_omission_count,
        "hallucinated_constraint_count": report.hallucinated_constraint_count,
        "over_optimization_count": report.over_optimization_count,
        "category_summaries": [
            {
                "category": item.category.value,
                "total_cases": item.total_cases,
                "passed_cases": item.passed_cases,
                "preservation_pass_rate": item.preservation_pass_rate,
                "average_savings_rate": item.average_savings_rate,
                "harmful_omission_count": item.harmful_omission_count,
                "hallucinated_constraint_count": item.hallucinated_constraint_count,
                "over_optimization_count": item.over_optimization_count,
                "savings_floor_failures": item.savings_floor_failures,
            }
            for item in report.category_summaries
        ],
        "results": [
            {
                "name": result.name,
                "category": result.category.value,
                "passed": result.passed,
                "preservation_passed": result.preservation_passed,
                "behavior_passed": result.behavior_passed,
                "hallucination_passed": result.hallucination_passed,
                "savings_passed": result.savings_passed,
                "savings_rate": result.savings_rate,
                "original_tokens": result.original_tokens,
                "optimized_tokens": result.optimized_tokens,
                "missing_terms": list(result.missing_terms),
                "missing_behaviors": list(result.missing_behaviors),
                "hallucinated_terms": list(result.hallucinated_terms),
                "over_optimized": result.over_optimized,
            }
            for result in report.results
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if report.passed_cases == report.total_cases else 1


if __name__ == "__main__":
    raise SystemExit(main())
