from fastapi.testclient import TestClient

from scrooge.config import Settings
from scrooge.main import app
from scrooge.schemas import CompatibilityRunRequest
from scrooge.storage import UsageStore


def test_compatibility_status_starts_pending_and_records_verified_run(tmp_path) -> None:
    db_path = tmp_path / "scrooge.db"
    store = UsageStore(Settings(SCROOGE_DATABASE_URL=f"sqlite:///{db_path}"))

    initial = store.compatibility_status()
    codex_initial = next(item for item in initial["targets"] if item["target_app"] == "codex_desktop")
    assert initial["overall_status"] == "pending_real_test"
    assert codex_initial["status"] == "pending_real_test"

    run = store.record_compatibility_run(
        CompatibilityRunRequest(
            target_app="codex_desktop",
            attempts=100,
            successes=99,
            failures=1,
            prompt_loss_count=0,
            failure_reasons=["one_focus_loss"],
        )
    )
    updated = store.compatibility_status()
    codex_updated = next(item for item in updated["targets"] if item["target_app"] == "codex_desktop")

    assert run["status"] == "verified"
    assert updated["overall_status"] == "verified"
    assert codex_updated["success_rate"] == 0.99
    assert codex_updated["failure_reasons"] == ["one_focus_loss"]


def test_security_scan_redacts_high_risk_values() -> None:
    response = TestClient(app).post(
        "/api/security/scan",
        json={
            "prompt": "Call API with password=supersecret and key sk-abcdef0123456789XYZ user kim@example.com"
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["safe_to_store_body"] is False
    assert len(payload["findings"]) >= 2
    assert "supersecret" not in payload["redacted_prompt"]
    assert "sk-abcdef0123456789XYZ" not in payload["redacted_prompt"]


def test_admin_policy_and_diagnostics_exclude_prompt_body() -> None:
    client = TestClient(app)

    policy = client.get("/api/admin/policy")
    diagnostics = client.get("/api/diagnostics/bundle")

    assert policy.status_code == 200
    assert policy.json()["diagnostics_include_prompt_body"] is False
    assert policy.json()["security_scan_required"] is True
    assert diagnostics.status_code == 200
    payload = diagnostics.json()
    assert payload["prompt_body_included"] is False
    assert "runtime" in payload
    assert "dashboard" in payload
    assert "compatibility" in payload
    assert "policy" in payload
