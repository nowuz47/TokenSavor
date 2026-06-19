"""Validate Scrooge savings math with calculator-building Codex prompts.

The script intentionally uses the same local API that the UI uses, then
recomputes token savings, rates, costs, audit rows, and summary totals.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrooge.pricing import get_pricing_registry  # noqa: E402

PROVIDER = "openai"
MODEL = "gpt-5.4-mini"
EXPECTED_OUTPUT_TOKENS = 1000

CALCULATOR_PROMPTS = {
    "calculator_simple": (
        "파이썬으로 안전한 CLI 계산기를 만들어주세요. "
        "사칙연산, 괄호, 음수를 지원하고 pytest 테스트도 작성해 주세요."
    ),
    "calculator_noisy_context": "\n".join(
        [
            "Codex에게 요청: 파이썬으로 안전한 CLI 계산기를 만들어주세요.",
            "요구사항: 사칙연산, 괄호, 음수, 잘못된 입력 오류 메시지.",
            "요구사항: 사칙연산, 괄호, 음수, 잘못된 입력 오류 메시지.",
            "요구사항: 사칙연산, 괄호, 음수, 잘못된 입력 오류 메시지.",
            "현재 초안:",
            "def add(a, b): return a + b",
            "def add(a, b): return a + b",
            "def subtract(a, b): return a - b",
            "ERROR calculator.py: unsupported token '**'",
            "ERROR calculator.py: unsupported token '**'",
            "ERROR calculator.py: unsupported token '**'",
            "출력 형식은 코드 변경 요약, 테스트, 실행 방법 순서로 주세요.",
        ]
    ),
    "codex_calculator_app_request": "\n".join(
        [
            "Please implement a real browser calculator app in this repository as if you were Codex.",
            "Requirements:",
            "- Use plain HTML, CSS, and JavaScript with no framework or build step.",
            "- Provide a calculator UI with a display, digit keys, decimal key, operators, clear, delete, and equals.",
            "- Support +, -, *, /, %, exponentiation, parentheses, decimals, and negative numbers.",
            "- Keep the core arithmetic parser separate from DOM code so it can be tested with Node.",
            "- Add tests for precedence, parentheses, unary minus, exponent associativity, bad input, and divide by zero.",
            "- Make the UI usable on a narrow mobile viewport and avoid overflowing display text.",
            "- Return the changed files, how to run the app, and how to run tests.",
            "",
            "Existing rough notes from the team:",
            "The display overflows on long results.",
            "The display overflows on long results.",
            "The old prototype used eval(), which is not allowed.",
            "The old prototype used eval(), which is not allowed.",
            "Bug report: 2 + 2 * 3 should be 8 but the prototype returned 12.",
            "Bug report: 2 + 2 * 3 should be 8 but the prototype returned 12.",
            "Bug report: -4 + 10 / 2 should be 1 but unary minus failed.",
            "Bug report: -4 + 10 / 2 should be 1 but unary minus failed.",
            "",
            "Current prototype snippets:",
            "function calculate(expr) { return eval(expr); }",
            "function calculate(expr) { return eval(expr); }",
            "button.onclick = () => display.innerText += button.innerText;",
            "button.onclick = () => display.innerText += button.innerText;",
            "",
            "Please keep the implementation small, readable, and easy to audit.",
        ]
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8750")
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for name, prompt in CALCULATOR_PROMPTS.items():
        response = post_json(
            args.api,
            "/api/optimize",
            {
                "prompt": prompt,
                "provider": PROVIDER,
                "model": MODEL,
                "task_type": task_type_for_case(name),
                "expected_output_tokens": EXPECTED_OUTPUT_TOKENS,
            },
        )
        assert_savings_math(response)
        post_json(args.api, f"/api/approvals/{response['request_id']}/approve", {"approved": True})
        results.append(
            {
                "case": name,
                "request_id": response["request_id"],
                "original_tokens": response["original_tokens"]["input_tokens"],
                "optimized_tokens": response["optimized_tokens"]["input_tokens"],
                "saved_tokens": response["saved_tokens"],
                "savings_rate": response["savings_rate"],
                "saved_cost_usd": response["saved_cost_usd"],
                "pricing_version": response["optimized_cost"]["pricing_version"],
            }
        )

    records = get_json(args.api, "/api/audit/records?limit=10000")
    summary = get_json(args.api, "/api/dashboard/summary?period=all")
    assert_audit_records(results, records)
    assert_summary_matches_records(summary, records)

    print(json.dumps({"validated": results, "summary": summary}, ensure_ascii=False, indent=2))
    return 0


def task_type_for_case(name: str) -> str:
    if name == "calculator_simple":
        return "test_generation"
    if name == "codex_calculator_app_request":
        return "general"
    return "bug_analysis"


def assert_savings_math(response: dict[str, Any]) -> None:
    original_tokens = response["original_tokens"]["input_tokens"]
    optimized_tokens = response["optimized_tokens"]["input_tokens"]
    expected_saved_tokens = max(0, original_tokens - optimized_tokens)
    expected_savings_rate = round(expected_saved_tokens / original_tokens, 4) if original_tokens else 0

    assert response["saved_tokens"] == expected_saved_tokens
    assert response["savings_rate"] == expected_savings_rate

    price = get_pricing_registry().get(PROVIDER, MODEL)
    output_cost = round(EXPECTED_OUTPUT_TOKENS * price.output_per_million_usd / 1_000_000, 8)
    expected_original_total = round(
        round(original_tokens * price.input_per_million_usd / 1_000_000, 8) + output_cost,
        8,
    )
    expected_optimized_total = round(
        round(optimized_tokens * price.input_per_million_usd / 1_000_000, 8) + output_cost,
        8,
    )
    expected_saved_cost = round(max(0.0, expected_original_total - expected_optimized_total), 8)

    assert response["original_cost"]["total_cost_usd"] == expected_original_total
    assert response["optimized_cost"]["total_cost_usd"] == expected_optimized_total
    assert response["saved_cost_usd"] == expected_saved_cost
    assert response["optimized_cost"]["pricing_version"] == price.version


def assert_audit_records(results: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    by_id = {record["request_id"]: record for record in records}
    for result in results:
        record = by_id[result["request_id"]]
        assert record["state"] == "sent"
        assert record["original_tokens"] == result["original_tokens"]
        assert record["optimized_tokens"] == result["optimized_tokens"]
        assert record["saved_tokens"] == result["saved_tokens"]
        assert record["savings_rate"] == result["savings_rate"]
        assert record["pricing_version"] == result["pricing_version"]


def assert_summary_matches_records(summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
    assert summary["total_requests"] == len(records)
    assert summary["approved_requests"] == sum(1 for record in records if record["state"] in {"sent", "measured"})
    assert summary["rejected_requests"] == sum(1 for record in records if record["state"] == "rejected")

    original_tokens = sum(record["original_tokens"] for record in records)
    optimized_tokens = sum(record["optimized_tokens"] for record in records)
    saved_tokens = sum(record["saved_tokens"] for record in records)
    saved_cost = round(sum(record["saved_cost_usd"] for record in records), 8)

    assert summary["original_tokens"] == original_tokens
    assert summary["optimized_tokens"] == optimized_tokens
    assert summary["saved_tokens"] == saved_tokens
    assert summary["saved_cost_usd"] == saved_cost
    expected_rate = round(saved_tokens / original_tokens, 4) if original_tokens else 0
    assert summary["savings_rate"] == expected_rate


def post_json(api_base: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return request_json(request)


def get_json(api_base: str, path: str) -> Any:
    request = urllib.request.Request(f"{api_base}{path}")
    return request_json(request)


def request_json(request: urllib.request.Request) -> Any:
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(f"Scrooge API is not reachable: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
