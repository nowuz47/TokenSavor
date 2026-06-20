from scrooge.config import Settings
from scrooge.optimizer import optimize_prompt
from scrooge.schemas import MeasurementRequest, OptimizeRequest, UsageState
from scrooge.storage import UsageStore


def test_storage_records_preview_without_prompt_body_by_default(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    response = optimize_prompt(OptimizeRequest(prompt="Please review this code", provider="openai"))

    store.save_preview(response, provider="openai", model="gpt-5.4-mini")
    store.mark_state(response.request_id, UsageState.SENT)
    measurement = store.record_measurement(
        response.request_id,
        MeasurementRequest(
            measured_original_tokens=response.original_tokens.input_tokens + 2,
            measured_input_tokens=max(0, response.optimized_tokens.input_tokens - 1),
            measured_output_tokens=123,
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

    assert records[no_savings.request_id]["rejection_reason"] == "no_savings"
    assert records[user_choice.request_id]["rejection_reason"] == "user_kept_original"
