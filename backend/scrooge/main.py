from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from scrooge.config import Settings, get_settings
from scrooge.optimizer import optimize_prompt
from scrooge.pricing import get_pricing_registry
from scrooge.proxy import router as proxy_router
from scrooge.quality import evaluate_quality_report
from scrooge.schemas import (
    AuditRecordSummary,
    ApprovalRequest,
    ApprovalResponse,
    DashboardSummary,
    MeasurementRequest,
    MeasurementResponse,
    OptimizeRequest,
    OptimizeResponse,
    QualitySummary,
    UsageState,
)
from scrooge.storage import UsageStore

app = FastAPI(title="Scrooge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d+)?|tauri://localhost)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(proxy_router)


@lru_cache
def get_store() -> UsageStore:
    return UsageStore(get_settings())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/optimize", response_model=OptimizeResponse)
def optimize(
    request: OptimizeRequest,
    settings: Settings = Depends(get_settings),
    store: UsageStore = Depends(get_store),
) -> OptimizeResponse:
    provider = request.provider or settings.default_provider
    model = request.model or settings.default_model
    normalized = request.model_copy(update={"provider": provider, "model": model})
    response = optimize_prompt(normalized)
    store.save_preview(response, provider=provider, model=model)
    return response


@app.post("/api/approvals/{request_id}/approve", response_model=ApprovalResponse)
def approve_request(
    request_id: str,
    approval: ApprovalRequest,
    store: UsageStore = Depends(get_store),
) -> ApprovalResponse:
    state = UsageState.SENT if approval.approved else UsageState.REJECTED
    try:
        notes = approval.notes
        if not approval.approved and not notes:
            notes = "user_kept_original"
        store.mark_state(request_id, state, notes=notes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="request_id not found") from exc
    return ApprovalResponse(request_id=request_id, state=state)


@app.post("/api/audit/records/{request_id}/measurement", response_model=MeasurementResponse)
def record_measurement(
    request_id: str,
    measurement: MeasurementRequest,
    store: UsageStore = Depends(get_store),
) -> MeasurementResponse:
    try:
        return MeasurementResponse(**store.record_measurement(request_id, measurement))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="request_id not found") from exc


@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(period: str = "month", store: UsageStore = Depends(get_store)) -> DashboardSummary:
    if period not in {"day", "week", "month", "all"}:
        raise HTTPException(status_code=400, detail="period must be day, week, month, or all")
    summary = store.summary(period=period)
    quality = evaluate_quality_report()
    summary["quality_preservation_rate"] = quality.quality_preservation_rate
    return DashboardSummary(**summary)


@app.get("/api/quality/summary", response_model=QualitySummary)
def quality_summary() -> QualitySummary:
    report = evaluate_quality_report()
    return QualitySummary(
        total_cases=report.total_cases,
        passed_cases=report.passed_cases,
        quality_preservation_rate=report.quality_preservation_rate,
        average_savings_rate=report.average_savings_rate,
        harmful_omission_count=report.harmful_omission_count,
        hallucinated_constraint_count=report.hallucinated_constraint_count,
        over_optimization_count=report.over_optimization_count,
        category_summaries=[
            {
                "category": item.category.value,
                "total_cases": item.total_cases,
                "passed_cases": item.passed_cases,
                "preservation_pass_rate": item.preservation_pass_rate,
                "average_savings_rate": item.average_savings_rate,
                "harmful_omission_count": item.harmful_omission_count,
                "hallucinated_constraint_count": item.hallucinated_constraint_count,
                "over_optimization_count": item.over_optimization_count,
                "savings_floor_failures": item.savings_floor_failures,
            }
            for item in report.category_summaries
        ],
        results=[
            {
                "name": item.name,
                "category": item.category.value,
                "passed": item.passed,
                "preservation_passed": item.preservation_passed,
                "behavior_passed": item.behavior_passed,
                "hallucination_passed": item.hallucination_passed,
                "savings_passed": item.savings_passed,
                "savings_rate": item.savings_rate,
                "original_tokens": item.original_tokens,
                "optimized_tokens": item.optimized_tokens,
                "missing_terms": list(item.missing_terms),
                "missing_behaviors": list(item.missing_behaviors),
                "hallucinated_terms": list(item.hallucinated_terms),
                "short_prompt": item.short_prompt,
                "over_optimized": item.over_optimized,
            }
            for item in report.results
        ],
    )


@app.get("/api/audit/records", response_model=list[AuditRecordSummary])
def audit_records(limit: int = 100, store: UsageStore = Depends(get_store)) -> list[AuditRecordSummary]:
    return [AuditRecordSummary(**record) for record in store.list_records(limit=limit)]


@app.delete("/api/audit/records")
def clear_audit_records(store: UsageStore = Depends(get_store)) -> dict[str, bool]:
    store.clear_records()
    return {"cleared": True}


@app.get("/api/pricing")
def pricing() -> dict[str, object]:
    registry = get_pricing_registry()
    return {
        "models": [
            {
                "provider": item.provider,
                "model": item.model,
                "input_per_million_usd": item.input_per_million_usd,
                "cached_input_per_million_usd": item.cached_input_per_million_usd,
                "output_per_million_usd": item.output_per_million_usd,
                "version": item.version,
                "effective_date": item.effective_date,
                "source_url": item.source_url,
            }
            for item in registry.list_models()
        ]
    }
