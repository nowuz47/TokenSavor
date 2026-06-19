from scrooge.config import Settings
from scrooge.optimizer import optimize_prompt
from scrooge.schemas import OptimizeRequest, UsageState
from scrooge.storage import UsageStore


def test_storage_records_preview_without_prompt_body_by_default(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    settings = Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}", SCROOGE_STORE_PROMPT_BODIES=False)
    store = UsageStore(settings)
    response = optimize_prompt(OptimizeRequest(prompt="Please review this code", provider="openai"))

    store.save_preview(response, provider="openai", model="gpt-5.4-mini")
    store.mark_state(response.request_id, UsageState.SENT)
    summary = store.summary("all")
    records = store.list_records()

    assert summary["total_requests"] == 1
    assert summary["approved_requests"] == 1
    assert summary["original_tokens"] > 0
    assert len(records) == 1
    assert records[0]["request_id"] == response.request_id
    assert records[0]["state"] == UsageState.SENT.value

    store.clear_records()
    assert store.summary("all")["total_requests"] == 0
    assert store.list_records() == []
