from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from scrooge.config import Settings, get_settings
from scrooge.optimizer import optimize_prompt
from scrooge.pricing import get_pricing_registry
from scrooge.proxy import router as proxy_router
from scrooge.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    DashboardSummary,
    OptimizeRequest,
    OptimizeResponse,
    UsageState,
)
from scrooge.storage import UsageStore

app = FastAPI(title="Scrooge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://127.0.0.1:1420"],
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
    store.mark_state(request_id, state)
    return ApprovalResponse(request_id=request_id, state=state)


@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(period: str = "month", store: UsageStore = Depends(get_store)) -> DashboardSummary:
    if period not in {"day", "week", "month", "all"}:
        raise HTTPException(status_code=400, detail="period must be day, week, month, or all")
    return DashboardSummary(**store.summary(period=period))


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

