from fastapi.testclient import TestClient

from scrooge.main import app


def test_quality_summary_endpoint_reports_category_floors() -> None:
    response = TestClient(app).get("/api/quality/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cases"] >= 50
    assert payload["passed_cases"] == payload["total_cases"]
    assert payload["harmful_omission_count"] == 0
    assert payload["hallucinated_constraint_count"] == 0
    assert payload["over_optimization_count"] == 0

    categories = {item["category"]: item for item in payload["category_summaries"]}
    assert set(categories) == {"coding", "debugging", "logs", "data", "docs_planning"}
    for item in categories.values():
        assert item["total_cases"] >= 10
        assert item["preservation_pass_rate"] >= 0.95
        assert item["savings_floor_failures"] == 0


def test_unknown_approval_returns_404() -> None:
    response = TestClient(app).post(
        "/api/approvals/missing-request/approve",
        json={"approved": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "request_id not found"


def test_installed_tauri_origin_can_call_optimize_endpoint() -> None:
    client = TestClient(app)
    origin = "http://tauri.localhost"
    preflight = client.options(
        "/api/optimize",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin

    response = client.post(
        "/api/optimize",
        headers={"Origin": origin},
        json={
            "prompt": "파이썬 계산기를 만들어주세요. eval() 금지, 0으로 나누기 처리, pytest 포함.",
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "task_type": None,
            "expected_output_tokens": 1000,
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    payload = response.json()
    assert payload["optimized_prompt"]
    assert payload["saved_tokens"] >= 0
