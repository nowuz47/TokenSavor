"""Validate controlled text attachment savings through the public API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AttachmentCase:
    name: str
    filename: str
    mime_type: str
    prompt: str
    content: str
    must_preserve: tuple[str, ...]
    min_attachment_savings_rate: float


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8750")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    health = get_json(args.api, "/health")
    assert health["status"] == "ok"
    summary_before = get_json(args.api, "/api/dashboard/summary?period=all")
    require_attachment_fields(summary_before)

    cases = [exercise_case(args.api, case) for case in build_cases()]
    records = get_json(args.api, "/api/audit/records?limit=10000")
    summary_after = get_json(args.api, "/api/dashboard/summary?period=all")
    require_attachment_fields(summary_after)

    request_ids = {case["request_id"] for case in cases}
    matching_records = [record for record in records if record["request_id"] in request_ids]
    assert len(matching_records) == len(cases)
    for record in matching_records:
        assert record["attachment_token_status"] == "measured"
        assert record["attachment_measurement_source"] == "measured_controlled"
        assert record["attachment_original_tokens"] >= record["attachment_optimized_tokens"]
        assert record["attachment_saved_tokens"] == (
            record["attachment_original_tokens"] - record["attachment_optimized_tokens"]
        )

    assert summary_after["attachment_measured_coverage"] > 0
    assert summary_after["attachment_saved_tokens"] >= sum(case["attachment_saved_tokens"] for case in cases)

    report = {
        "api": args.api,
        "cases": cases,
        "summary_before": summary_before,
        "summary_after": summary_after,
        "matching_records": matching_records,
        "pass": True,
    }
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def build_cases() -> list[AttachmentCase]:
    log_content = "\n".join(
        ["2026-06-21 09:00:00 ERROR payment-api timeout order_id=1001 latency=5300ms" for _ in range(1000)]
        + ['File "/app/payment.py", line 42, in charge']
        + ["TimeoutError: payment gateway timeout"]
    )
    csv_rows = ["business_unit,region,product,revenue,year,quarter"]
    csv_rows.extend(f"enterprise,seoul,product-{index % 8},{100000 - index * 17},2026,Q1" for index in range(600))
    json_items = [
        {
            "id": f"evt-{index}",
            "status": "failed" if index % 7 == 0 else "ok",
            "latency_ms": 120 + index,
            "error": "gateway_timeout" if index % 7 == 0 else None,
            "service": "checkout",
        }
        for index in range(500)
    ]
    calculator_py = "\n".join(
        [
            "def add(a, b): return a + b",
            "def subtract(a, b): return a - b",
            "def multiply(a, b): return a * b",
            "def divide(a, b):",
            "    if b == 0:",
            "        raise ZeroDivisionError('divide by zero')",
            "    return a / b",
            "def unsafe(expr):",
            "    return eval(expr)",
        ]
        + ["# repeated legacy calculator helper" for _ in range(80)]
    )
    short_md = "# Runbook\n- Check health\n- Restart worker only after confirming queue drain"
    return [
        AttachmentCase(
            name="large_error_log",
            filename="large-error.log",
            mime_type="text/plain",
            prompt="Analyze the attached large-error.log. Preserve the file, line, exception, root cause, and next checks.",
            content=log_content,
            must_preserve=("large-error.log", "TimeoutError", "payment.py", "line 42"),
            min_attachment_savings_rate=0.3,
        ),
        AttachmentCase(
            name="orders_csv",
            filename="orders.csv",
            mime_type="text/csv",
            prompt="Analyze orders.csv for revenue drops by business_unit, region, product, year, and quarter.",
            content="\n".join(csv_rows),
            must_preserve=("orders.csv", "business_unit", "region", "revenue"),
            min_attachment_savings_rate=0.2,
        ),
        AttachmentCase(
            name="payload_json",
            filename="payload.json",
            mime_type="application/json",
            prompt="Summarize payload.json failures and preserve status, error, latency_ms, service, and id fields.",
            content=json.dumps({"events": json_items}, ensure_ascii=False),
            must_preserve=("payload.json", "status", "gateway_timeout", "latency_ms"),
            min_attachment_savings_rate=0.2,
        ),
        AttachmentCase(
            name="calculator_code",
            filename="calculator.py",
            mime_type="text/x-python",
            prompt="Review calculator.py. Preserve divide by zero handling and flag eval() risk.",
            content=calculator_py,
            must_preserve=("calculator.py", "divide", "ZeroDivisionError", "eval"),
            min_attachment_savings_rate=0,
        ),
        AttachmentCase(
            name="short_markdown",
            filename="short.md",
            mime_type="text/markdown",
            prompt="Review short.md and keep the steps intact.",
            content=short_md,
            must_preserve=("short.md", "queue drain"),
            min_attachment_savings_rate=0,
        ),
    ]


def exercise_case(api: str, case: AttachmentCase) -> dict[str, Any]:
    response = post_json(
        api,
        "/api/optimize",
        {
            "prompt": case.prompt,
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "expected_output_tokens": 1000,
            "attachments": [
                {
                    "name": case.filename,
                    "mime_type": case.mime_type,
                    "size_bytes": len(case.content.encode("utf-8")),
                    "content": case.content,
                    "token_status": "unknown",
                }
            ],
        },
    )
    summary = response["attachment_summary"]
    assert summary["token_status"] == "measured", case.name
    assert summary["attachment_measurement_source"] == "measured_controlled", case.name
    assert summary["attachment_savings_rate"] >= case.min_attachment_savings_rate, case.name
    assert response["saved_tokens"] == max(
        0,
        response["original_tokens"]["input_tokens"] - response["optimized_tokens"]["input_tokens"],
    )
    for term in case.must_preserve:
        assert term.lower() in response["optimized_prompt"].lower(), f"{case.name} missing {term}"

    measurement = post_json(
        api,
        f"/api/audit/records/{response['request_id']}/measurement",
        {
            "measured_original_tokens": response["original_tokens"]["input_tokens"],
            "measured_input_tokens": response["optimized_tokens"]["input_tokens"],
            "measured_total_input_tokens": response["optimized_tokens"]["input_tokens"],
            "measured_output_tokens": 1000,
            "source": "measured_controlled",
        },
    )
    assert measurement["state"] == "measured"
    return {
        "name": case.name,
        "request_id": response["request_id"],
        "attachment_original_tokens": summary["attachment_original_tokens"],
        "attachment_optimized_tokens": summary["attachment_optimized_tokens"],
        "attachment_saved_tokens": summary["attachment_saved_tokens"],
        "attachment_savings_rate": summary["attachment_savings_rate"],
        "total_savings_rate": summary["total_savings_rate"],
    }


def require_attachment_fields(summary: dict[str, Any]) -> None:
    required = {
        "attachment_requests",
        "attachment_unknown_requests",
        "attachment_measured_requests",
        "attachment_measured_coverage",
        "attachment_original_tokens",
        "attachment_optimized_tokens",
        "attachment_saved_tokens",
        "attachment_savings_rate",
    }
    missing = sorted(required - set(summary))
    if missing:
        raise AssertionError(f"installed backend is missing attachment dashboard fields: {missing}")


def get_json(api: str, path: str, expected_status: int = 200) -> dict[str, Any]:
    request = urllib.request.Request(f"{api}{path}", method="GET")
    return request_json(request, expected_status)


def post_json(api: str, path: str, body: dict[str, Any], expected_status: int = 200) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{api}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return request_json(request, expected_status)


def request_json(request: urllib.request.Request, expected_status: int) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == expected_status, payload
            return payload
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        assert exc.code == expected_status, payload
        return payload


if __name__ == "__main__":
    sys.exit(main())
