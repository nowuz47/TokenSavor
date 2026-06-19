from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrooge.quality import evaluate_golden_suite  # noqa: E402


def main() -> int:
    results = evaluate_golden_suite()
    passed = sum(1 for result in results if result.passed)
    payload = {
        "passed": passed,
        "total": len(results),
        "quality_preservation_rate": round(passed / len(results), 4) if results else 0,
        "average_savings_rate": round(
            sum(result.savings_rate for result in results) / len(results),
            4,
        )
        if results
        else 0,
        "results": [
            {
                "name": result.name,
                "passed": result.passed,
                "savings_rate": result.savings_rate,
                "original_tokens": result.original_tokens,
                "optimized_tokens": result.optimized_tokens,
                "missing_terms": list(result.missing_terms),
            }
            for result in results
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
