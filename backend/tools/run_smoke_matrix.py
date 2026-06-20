"""Run broad API smoke checks against a Scrooge backend.

The matrix intentionally covers realistic desktop flows: optimization preview,
approval/rejection, measured usage, dashboard aggregation, quality summary, and
proxy capture. It uses only the public HTTP API so it can validate either a
dev server or an installed sidecar. Existing audit records are preserved by
default; pass --reset-records only against an isolated test database.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SmokeCase:
    name: str
    prompt: str
    expected_task_type: str
    must_preserve: tuple[str, ...]
    approve: bool | None = None
    min_savings_rate: float = 0
    measure: bool = False


def repeated(line: str, count: int) -> list[str]:
    return [line for _ in range(count)]


SMOKE_CASES: tuple[SmokeCase, ...] = (
    SmokeCase(
        name="ko_short_calculator_no_overopt",
        prompt=(
            "계산기 앱을 파이썬으로 만들어주세요. eval()은 쓰지 말고, "
            "0으로 나누기 예외와 pytest 테스트를 포함해 주세요."
        ),
        expected_task_type="general",
        must_preserve=("파이썬", "eval()", "0으로 나누기", "pytest"),
        approve=False,
    ),
    SmokeCase(
        name="ko_enterprise_data_analysis",
        prompt=(
            "sales_2026_q1.csv를 분석해서 사업부, 지역, 상품군별 매출 증감률을 구하고, "
            "전년 동기 대비 15% 이상 하락한 항목을 찾아주세요. 컬럼은 business_unit, "
            "region, product, revenue, year, quarter 입니다."
        ),
        expected_task_type="data_analysis",
        must_preserve=("sales_2026_q1.csv", "business_unit", "region", "전년 동기 대비 15%"),
        approve=False,
    ),
    SmokeCase(
        name="ko_dashboard_bug",
        prompt=(
            "Tauri 앱에서 단축키 Ctrl+Alt+S를 눌러도 대시보드의 사용 로그와 절감 토큰이 "
            "바로 반영되지 않는 버그를 찾아주세요. 이벤트 emit, frontend refresh, "
            "SQLite audit record 저장 여부를 기준으로 확인해 주세요."
        ),
        expected_task_type="bug_analysis",
        must_preserve=("Ctrl+Alt+S", "대시보드", "SQLite audit record"),
        approve=False,
    ),
    SmokeCase(
        name="ko_repeated_payment_logs",
        prompt="\n".join(
            ["아래 운영 로그를 분석해서 장애 원인, 영향 범위, 즉시 조치, 재발 방지책을 정리해 주세요."]
            + repeated("2026-06-20 09:01:11 ERROR payment-api timeout order_id=1001 pg=KCP latency=5300ms", 80)
            + ["CloudWatch 기준이며 배포 직후 5분 동안만 발생했습니다."]
        ),
        expected_task_type="log_analysis",
        must_preserve=("payment-api", "KCP", "CloudWatch", "배포 직후 5분"),
        approve=True,
        min_savings_rate=0.2,
        measure=True,
    ),
    SmokeCase(
        name="en_large_diff_review",
        prompt="\n".join(
            ["Review this auth diff for security regressions.", "diff --git a/auth.py b/auth.py", "@@ -10,7 +10,7 @@"]
            + repeated("- return user.is_admin", 60)
            + repeated("+ return True", 60)
        ),
        expected_task_type="code_review",
        must_preserve=("diff --git", "@@", "auth.py", "return True"),
        approve=True,
        min_savings_rate=0.2,
    ),
    SmokeCase(
        name="en_stacktrace_bug",
        prompt="\n".join(
            ["Investigate this stack trace."]
            + repeated('File "/app/scrooge/optimizer.py", line 132, in normalize_prompt', 70)
            + repeated("ValueError: invalid template marker", 70)
        ),
        expected_task_type="log_analysis",
        must_preserve=("ValueError", "normalize_prompt", "line 132"),
        approve=True,
        min_savings_rate=0.2,
    ),
    SmokeCase(
        name="en_docs_trust_policy",
        prompt="Draft trust policy: team-level metrics, prompt hash only, local storage by default.",
        expected_task_type="architecture_review",
        must_preserve=("team-level", "hash", "local storage"),
        approve=False,
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8750")
    parser.add_argument("--mode", choices=("smoke", "soak"), default="smoke")
    parser.add_argument("--duration-sec", type=int, default=120)
    parser.add_argument("--interval-sec", type=int, default=10)
    parser.add_argument(
        "--reset-records",
        action="store_true",
        help="Delete existing audit records before running. Use only with an isolated test DB.",
    )
    parser.add_argument("--keep-records", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    health = get_json(args.api, "/health")
    assert health["status"] == "ok"

    if args.reset_records and args.keep_records:
        parser.error("--reset-records and --keep-records cannot be used together")

    if args.reset_records:
        delete_json(args.api, "/api/audit/records")
        empty_summary = get_json(args.api, "/api/dashboard/summary?period=all")
        assert empty_summary["total_requests"] == 0
        assert empty_summary["saved_tokens"] == 0

    unknown_approval = post_json(
        args.api,
        "/api/approvals/missing-request/approve",
        {"approved": True},
        expected_status=404,
    )
    assert unknown_approval["detail"] == "request_id not found"

    invalid_period = get_json(args.api, "/api/dashboard/summary?period=quarter", expected_status=400)
    assert "period must be" in invalid_period["detail"]

    results = [exercise_case(args.api, case) for case in SMOKE_CASES]
    proxy_result = exercise_proxy_capture(args.api)

    records = get_json(args.api, "/api/audit/records?limit=10000")
    summary = get_json(args.api, "/api/dashboard/summary?period=all")
    quality = get_json(args.api, "/api/quality/summary")
    pricing = get_json(args.api, "/api/pricing")
    runtime = get_json(args.api, "/api/runtime/status")
    compatibility = get_json(args.api, "/api/compatibility/status")
    policy = get_json(args.api, "/api/admin/policy")
    diagnostics = get_json(args.api, "/api/diagnostics/bundle")
    security_scan = post_json(
        args.api,
        "/api/security/scan",
        {"prompt": "Never store password=supersecret or key sk-abcdef0123456789XYZ in audit logs."},
    )
    category_summary = get_json(args.api, "/api/dashboard/category-summary?period=all")

    assert quality["passed_cases"] == quality["total_cases"]
    assert any(item["model"] == "gpt-5.4-mini" for item in pricing["models"])
    assert runtime["backend_status"] == "ok"
    assert runtime["database_status"] == "ok"
    assert compatibility["overall_status"] in {"pending_real_test", "limited", "verified", "failed"}
    assert any(item["target_app"] == "codex_desktop" for item in compatibility["targets"])
    assert policy["diagnostics_include_prompt_body"] is False
    assert policy["security_scan_required"] is True
    assert diagnostics["prompt_body_included"] is False
    assert diagnostics["compatibility"]["overall_status"] == compatibility["overall_status"]
    assert security_scan["safe_to_store_body"] is False
    assert "supersecret" not in security_scan["redacted_prompt"]
    assert isinstance(category_summary, list)
    assert_summary_matches_records(summary, records)

    by_id = {record["request_id"]: record for record in records}
    for result in results:
        record = by_id[result["request_id"]]
        assert record["task_type"] == result["task_type"]
        assert record["saved_tokens"] == result["saved_tokens"]
        if result["measured"]:
            assert record["state"] == "measured"
            assert record["token_error_rate"] is not None

    assert by_id[proxy_result["request_id"]]["state"] == "estimated"

    soak = run_soak(args.api, args.duration_sec, args.interval_sec) if args.mode == "soak" else None

    output = {
        "mode": args.mode,
        "cases": results,
        "proxy": proxy_result,
        "runtime": runtime,
        "compatibility": compatibility,
        "policy": policy,
        "category_summary": category_summary,
        "soak": soak,
        "summary": summary,
        "quality": {
            "passed_cases": quality["passed_cases"],
            "total_cases": quality["total_cases"],
            "quality_preservation_rate": quality["quality_preservation_rate"],
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def run_soak(api: str, duration_sec: int, interval_sec: int) -> dict[str, Any]:
    started_at = time.time()
    deadline = started_at + max(1, duration_sec)
    checks = 0
    health_successes = 0
    optimize_successes = 0
    failed_events: list[str] = []
    while time.time() < deadline:
        checks += 1
        try:
            health = get_json(api, "/health")
            if health["status"] == "ok":
                health_successes += 1
            response = post_json(
                api,
                "/api/optimize",
                {
                    "prompt": "Soak test: summarize repeated timeout logs.\nERROR worker timeout\nERROR worker timeout\nERROR worker timeout",
                    "provider": "openai",
                    "model": "gpt-5.4-mini",
                    "capture_source": "manual",
                },
            )
            if response["request_id"]:
                optimize_successes += 1
        except Exception as exc:  # pragma: no cover - defensive for installed app smoke.
            failed_events.append(str(exc))
        time.sleep(max(1, interval_sec))
    return {
        "duration_sec": round(time.time() - started_at, 2),
        "checks": checks,
        "health_success_rate": round(health_successes / checks, 4) if checks else 0,
        "optimize_success_rate": round(optimize_successes / checks, 4) if checks else 0,
        "failed_events": failed_events,
    }


def exercise_case(api: str, case: SmokeCase) -> dict[str, Any]:
    response = post_json(
        api,
        "/api/optimize",
        {
            "prompt": case.prompt,
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "expected_output_tokens": 1000,
        },
    )
    optimized_prompt = response["optimized_prompt"]

    assert response["task_type"] == case.expected_task_type, case.name
    assert response["savings_rate"] >= case.min_savings_rate, case.name
    assert response["saved_tokens"] == max(
        0,
        response["original_tokens"]["input_tokens"] - response["optimized_tokens"]["input_tokens"],
    )
    for term in case.must_preserve:
        assert term.lower() in optimized_prompt.lower(), f"{case.name} missing {term}"

    if case.approve is not None:
        post_json(api, f"/api/approvals/{response['request_id']}/approve", {"approved": case.approve})

    final_original_tokens = response["original_tokens"]["input_tokens"]
    final_optimized_tokens = response["optimized_tokens"]["input_tokens"]
    final_saved_tokens = response["saved_tokens"]
    final_savings_rate = response["savings_rate"]
    if case.measure:
        measured_input = response["optimized_tokens"]["input_tokens"] + 5
        measured_original = response["original_tokens"]["input_tokens"] + 10
        measurement = post_json(
            api,
            f"/api/audit/records/{response['request_id']}/measurement",
            {
                "measured_original_tokens": measured_original,
                "measured_input_tokens": measured_input,
                "measured_output_tokens": 1000,
                "source": "smoke_simulated_provider_usage",
            },
        )
        assert measurement["state"] == "measured"
        assert measurement["measured_input_tokens"] == measured_input
        final_original_tokens = measured_original
        final_optimized_tokens = measured_input
        final_saved_tokens = max(0, measured_original - measured_input)
        final_savings_rate = round(final_saved_tokens / measured_original, 4) if measured_original else 0

    return {
        "name": case.name,
        "request_id": response["request_id"],
        "task_type": response["task_type"],
        "original_tokens": final_original_tokens,
        "optimized_tokens": final_optimized_tokens,
        "saved_tokens": final_saved_tokens,
        "savings_rate": final_savings_rate,
        "measured": case.measure,
    }


def exercise_proxy_capture(api: str) -> dict[str, Any]:
    payload = {
        "model": "gpt-5.4-mini",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Analyze CloudWatch logs."},
                    {"type": "text", "text": "ERROR worker timeout\nERROR worker timeout\nERROR worker timeout"},
                ],
            },
        ],
    }
    response = post_json(api, "/proxy/openai/v1/chat/completions", payload)
    assert response["captured"] is True
    assert response["forwarded"] is False
    assert response["preview"]["task_type"] == "log_analysis"
    return {
        "request_id": response["request_id"],
        "captured": response["captured"],
        "forwarded": response["forwarded"],
        "task_type": response["preview"]["task_type"],
    }


def assert_summary_matches_records(summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
    assert summary["total_requests"] == len(records)
    assert summary["approved_requests"] == sum(1 for record in records if record["state"] in {"sent", "measured"})
    assert summary["rejected_requests"] == sum(1 for record in records if record["state"] == "rejected")
    assert summary["measured_requests"] == sum(1 for record in records if record["state"] == "measured")
    assert summary["original_tokens"] == sum(record["original_tokens"] for record in records)
    assert summary["optimized_tokens"] == sum(record["optimized_tokens"] for record in records)
    assert summary["saved_tokens"] == sum(record["saved_tokens"] for record in records)
    expected_saved_cost = round(sum(record["saved_cost_usd"] for record in records), 8)
    assert summary["saved_cost_usd"] == expected_saved_cost
    expected_rate = (
        round(summary["saved_tokens"] / summary["original_tokens"], 4)
        if summary["original_tokens"]
        else 0
    )
    assert summary["savings_rate"] == expected_rate


def request_json(
    api_base: str,
    path: str,
    *,
    method: str,
    payload: dict[str, Any] | None = None,
    expected_status: int = 200,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{api_base}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            assert response.status == expected_status
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        if exc.code != expected_status:
            raise
        return json.loads(body) if body else {}
    except urllib.error.URLError as exc:
        raise SystemExit(f"Scrooge API is not reachable: {exc}") from exc


def get_json(api_base: str, path: str, expected_status: int = 200) -> Any:
    return request_json(api_base, path, method="GET", expected_status=expected_status)


def post_json(
    api_base: str,
    path: str,
    payload: dict[str, Any],
    expected_status: int = 200,
) -> Any:
    return request_json(api_base, path, method="POST", payload=payload, expected_status=expected_status)


def delete_json(api_base: str, path: str, expected_status: int = 200) -> Any:
    return request_json(api_base, path, method="DELETE", expected_status=expected_status)


if __name__ == "__main__":
    raise SystemExit(main())
