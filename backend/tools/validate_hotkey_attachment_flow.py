"""Validate hotkey attachment telemetry through the public API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8750")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    health = get_json(args.api, "/health")
    assert health["status"] == "ok"

    readable = exercise_readable_attachment(args.api)
    unknown = exercise_unknown_attachment(args.api)
    records = get_json(args.api, "/api/audit/records?limit=10000")
    summary = get_json(args.api, "/api/dashboard/summary?period=all")

    request_ids = {readable["request_id"], unknown["request_id"]}
    matching_records = [record for record in records if record["request_id"] in request_ids]
    assert len(matching_records) == 2

    readable_record = next(record for record in matching_records if record["request_id"] == readable["request_id"])
    unknown_record = next(record for record in matching_records if record["request_id"] == unknown["request_id"])

    assert readable_record["capture_source"] == "hotkey"
    assert readable_record["attachment_token_status"] == "measured"
    assert readable_record["attachment_discovery_source"] == "workspace_match"
    assert readable_record["attachment_content_available_count"] == 1
    assert readable_record["attachment_saved_tokens"] > 0

    assert unknown_record["capture_source"] == "hotkey"
    assert unknown_record["attachment_token_status"] == "unknown"
    assert unknown_record["attachment_discovery_source"] == "prompt_reference"
    assert unknown_record["attachment_content_available_count"] == 0
    assert unknown_record["total_savings_rate"] is None

    assert summary["hotkey_discovered_attachments"] >= 2
    assert summary["hotkey_content_available_attachments"] >= 1
    assert summary["hotkey_unknown_attachments"] >= 1

    report = {
        "api": args.api,
        "readable": readable,
        "unknown": unknown,
        "matching_records": matching_records,
        "summary": summary,
        "pass": True,
    }
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def exercise_readable_attachment(api: str) -> dict[str, Any]:
    content = "\n".join(
        ["2026-06-21 09:00:00 ERROR checkout timeout order_id=1001 latency=5300ms" for _ in range(300)]
        + ['File "/app/checkout.py", line 77, in pay']
        + ["TimeoutError: checkout gateway timeout"]
    )
    response = post_json(
        api,
        "/api/optimize",
        {
            "prompt": "Analyze C:\\work\\large-error.log and preserve checkout.py line 77 and TimeoutError.",
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "capture_source": "hotkey",
            "attachments": [
                {
                    "name": "large-error.log",
                    "mime_type": "text/plain",
                    "size_bytes": len(content.encode("utf-8")),
                    "content": content,
                    "token_status": "unknown",
                    "discovery_source": "workspace_match",
                    "content_available": True,
                    "path_available": True,
                }
            ],
        },
    )
    summary = response["attachment_summary"]
    assert summary["token_status"] == "measured"
    assert summary["attachment_saved_tokens"] > 0
    assert "TimeoutError" in response["optimized_prompt"]
    post_json(
        api,
        "/api/hotkey/events",
        {
            "request_id": response["request_id"],
            "status": "optimized_pasted",
            "saved_tokens": response["saved_tokens"],
            "elapsed_ms": 350,
            "discovered_attachment_count": 1,
            "content_available_attachment_count": 1,
            "unknown_attachment_count": 0,
            "unsupported_attachment_count": 0,
        },
    )
    return {
        "request_id": response["request_id"],
        "attachment_saved_tokens": summary["attachment_saved_tokens"],
        "attachment_savings_rate": summary["attachment_savings_rate"],
    }


def exercise_unknown_attachment(api: str) -> dict[str, Any]:
    response = post_json(
        api,
        "/api/optimize",
        {
            "prompt": "첨부한 파일을 보고 장애 원인을 찾아주세요.",
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "capture_source": "hotkey",
            "attachments": [
                {
                    "name": "codex-attached-file",
                    "token_status": "unknown",
                    "discovery_source": "prompt_reference",
                    "content_available": False,
                    "path_available": False,
                    "read_error": "codex_attachment_body_not_exposed",
                }
            ],
        },
    )
    summary = response["attachment_summary"]
    assert summary["token_status"] == "unknown"
    assert summary["total_savings_rate"] is None
    post_json(
        api,
        "/api/hotkey/events",
        {
            "request_id": response["request_id"],
            "status": "no_savings_kept_original",
            "saved_tokens": 0,
            "elapsed_ms": 180,
            "discovered_attachment_count": 1,
            "content_available_attachment_count": 0,
            "unknown_attachment_count": 1,
            "unsupported_attachment_count": 0,
        },
    )
    return {"request_id": response["request_id"]}


def get_json(api: str, path: str) -> dict[str, Any] | list[dict[str, Any]]:
    request = urllib.request.Request(f"{api}{path}", method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(api: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{api}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    sys.exit(main())
