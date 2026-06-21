from scrooge.config import Settings
from scrooge.optimizer import optimize_prompt
from scrooge.schemas import (
    AttachmentMetadata,
    AttachmentTokenStatus,
    CaptureSource,
    HotkeyEventRequest,
    MeasurementRequest,
    OptimizeRequest,
    UsageState,
)
from scrooge.storage import UsageStore


def test_storage_records_preview_without_prompt_body_by_default(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    response = optimize_prompt(OptimizeRequest(prompt="Please review this code", provider="openai"))

    store.save_preview(response, provider="openai", model="gpt-5.4-mini", capture_source=CaptureSource.HOTKEY)
    store.mark_state(response.request_id, UsageState.SENT)
    measurement = store.record_measurement(
        response.request_id,
        MeasurementRequest(
            measured_original_tokens=response.original_tokens.input_tokens + 2,
            measured_input_tokens=max(0, response.optimized_tokens.input_tokens - 1),
            measured_output_tokens=123,
            source="openai_usage",
            upstream_status=200,
        ),
    )
    summary = store.summary("all")
    records = store.list_records()

    assert summary["total_requests"] == 1
    assert summary["approved_requests"] == 1
    assert summary["measured_requests"] == 1
    assert summary["measurement_coverage"] == 1
    assert summary["original_tokens"] > 0
    assert measurement["state"] == UsageState.MEASURED
    assert measurement["measured_input_tokens"] == records[0]["measured_input_tokens"]
    assert len(records) == 1
    assert records[0]["request_id"] == response.request_id
    assert records[0]["state"] == UsageState.MEASURED.value
    assert records[0]["provider_usage_source"] == "openai_usage"
    assert records[0]["upstream_status"] == 200
    assert records[0]["capture_source"] == "hotkey"
    assert records[0]["delivery_status"] == "measured"
    assert records[0]["measurement_status"] == "measured"
    assert records[0]["tokenizer_confidence"] == "provider_measured"
    assert records[0]["token_error_rate"] is not None

    store.clear_records()
    assert store.summary("all")["total_requests"] == 0
    assert store.list_records() == []


def test_storage_recreates_schema_after_sqlite_file_is_deleted(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    first = optimize_prompt(OptimizeRequest(prompt="Please review this code", provider="openai"))
    store.save_preview(first, provider="openai", model="gpt-5.4-mini")

    db_path.unlink()

    second = optimize_prompt(OptimizeRequest(prompt="ERROR payment-api timeout\nERROR payment-api timeout", provider="openai"))
    store.save_preview(second, provider="openai", model="gpt-5.4-mini")

    records = store.list_records()
    assert len(records) == 1
    assert records[0]["request_id"] == second.request_id


def test_mark_state_unknown_request_raises_key_error(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)

    try:
        store.mark_state("missing-request", UsageState.SENT)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown request_id should fail")


def test_rejected_records_include_reason_or_inferred_reason(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    no_savings = optimize_prompt(OptimizeRequest(prompt="짧은 요청", provider="openai"))
    user_choice = optimize_prompt(
        OptimizeRequest(
            prompt="ERROR worker timeout\nERROR worker timeout\nERROR worker timeout\nERROR worker timeout",
            provider="openai",
        )
    )

    store.save_preview(no_savings, provider="openai", model="gpt-5.4-mini")
    store.save_preview(user_choice, provider="openai", model="gpt-5.4-mini")
    store.mark_state(no_savings.request_id, UsageState.REJECTED)
    store.mark_state(user_choice.request_id, UsageState.REJECTED, notes="user_kept_original")

    records = {record["request_id"]: record for record in store.list_records()}

    assert records[no_savings.request_id]["rejection_reason"] == "no_savings_short_prompt"
    assert records[user_choice.request_id]["rejection_reason"] == "user_kept_original"


def test_summary_reports_hotkey_validation_and_short_prompt_protection(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)

    for index in range(30):
        response = optimize_prompt(
            OptimizeRequest(
                prompt=f"짧은 요청 {index}",
                provider="openai",
                capture_source=CaptureSource.HOTKEY,
            )
        )
        store.save_preview(response, provider="openai", model="gpt-5.4-mini", capture_source=CaptureSource.HOTKEY)
        store.mark_state(response.request_id, UsageState.REJECTED, notes="no_savings_short_prompt")

    summary = store.summary("all")

    assert summary["hotkey_attempts"] == 30
    assert summary["hotkey_failed_requests"] == 0
    assert summary["hotkey_success_rate"] == 1
    assert summary["hotkey_validation_status"] == "passed"
    assert summary["short_prompt_protected_count"] == 30


def test_hotkey_events_drive_recent_validation_and_delivery_status(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    response = optimize_prompt(
        OptimizeRequest(
            prompt="ERROR payment failed\nERROR payment failed\nERROR payment failed",
            provider="openai",
            capture_source=CaptureSource.HOTKEY,
        )
    )
    store.save_preview(response, provider="openai", model="gpt-5.4-mini", capture_source=CaptureSource.HOTKEY)

    store.record_hotkey_event(
        HotkeyEventRequest(
            request_id=response.request_id,
            status="optimized_pasted",
            saved_tokens=response.saved_tokens,
            elapsed_ms=420,
        )
    )
    for index in range(26):
        store.record_hotkey_event(HotkeyEventRequest(status="no_savings_kept_original", elapsed_ms=120 + index))
    for status in ("backend_failed", "clipboard_failed", "paste_failed"):
        store.record_hotkey_event(HotkeyEventRequest(status=status, failure_reason=status, elapsed_ms=500))

    summary = store.summary("all")
    record = store.list_records()[0]

    assert summary["hotkey_attempts"] == 30
    assert summary["hotkey_failed_requests"] == 3
    assert summary["hotkey_success_rate"] == 0.9
    assert summary["hotkey_validation_status"] == "passed"
    assert summary["latest_hotkey_status"] == "paste_failed"
    assert summary["used_assumed_requests"] == 1
    assert record["state"] == "sent"
    assert record["delivery_status"] == "pasted_assumed_used"
    assert record["measurement_status"] == "estimated"


def test_summary_counts_repeated_prompt_family_as_followup_request(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    prompt = (
        "파이썬 계산기 앱을 만들어주세요. eval()은 금지하고 0으로 나누기 처리를 포함하세요.\n"
        "pytest 테스트도 함께 작성해주세요."
    )
    first = optimize_prompt(OptimizeRequest(prompt=prompt, provider="openai"))
    second = optimize_prompt(OptimizeRequest(prompt=prompt, provider="openai"))

    store.save_preview(first, provider="openai", model="gpt-5.4-mini")
    store.save_preview(second, provider="openai", model="gpt-5.4-mini")
    store.mark_state(first.request_id, UsageState.SENT, upstream_status=200)
    store.mark_state(second.request_id, UsageState.SENT, upstream_status=200)

    summary = store.summary("all")

    assert summary["total_requests"] == 2
    assert summary["followup_requests"] == 1
    assert summary["reask_rate"] == 0.5


def test_storage_tracks_attachment_metadata_without_prompt_body(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    attachments = [
        AttachmentMetadata(
            name="orders.csv",
            mime_type="text/csv",
            size_bytes=4096,
            content_hash="sha256:orders",
            token_status=AttachmentTokenStatus.ESTIMATED,
            estimated_tokens=1200,
        )
    ]
    response = optimize_prompt(
        OptimizeRequest(
            prompt="Analyze the attached orders.csv and summarize revenue anomalies.",
            provider="openai",
            attachments=attachments,
        )
    )

    store.save_preview(response, provider="openai", model="gpt-5.4-mini", attachments=attachments)
    record = store.list_records()[0]
    summary = store.summary("all")

    assert record["attachment_count"] == 1
    assert record["attachment_token_status"] == "estimated"
    assert record["attachment_estimated_tokens"] == 1200
    assert record["total_savings_rate"] == response.total_savings_rate
    assert summary["attachment_requests"] == 1
    assert summary["attachment_unknown_requests"] == 0
    assert summary["attachment_measured_requests"] == 0


def test_measurement_marks_attachments_measured_when_total_input_is_available(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    attachments = [
        AttachmentMetadata(
            name="trace.log",
            token_status=AttachmentTokenStatus.UNKNOWN,
        )
    ]
    response = optimize_prompt(
        OptimizeRequest(
            prompt="Use the attached trace.log to find the exception.",
            provider="openai",
            attachments=attachments,
        )
    )

    store.save_preview(response, provider="openai", model="gpt-5.4-mini", attachments=attachments)
    store.record_measurement(
        response.request_id,
        MeasurementRequest(
            measured_original_tokens=response.original_tokens.input_tokens,
            measured_input_tokens=response.optimized_tokens.input_tokens,
            measured_total_input_tokens=response.optimized_tokens.input_tokens + 800,
            measured_output_tokens=42,
            source="openai_usage",
        ),
    )

    record = store.list_records()[0]
    summary = store.summary("all")

    assert record["attachment_token_status"] == "measured"
    assert record["attachment_measured_tokens"] == 800
    assert record["total_savings_rate"] is not None
    assert summary["attachment_requests"] == 1
    assert summary["attachment_measured_requests"] == 1
    assert summary["attachment_measured_coverage"] == 1
