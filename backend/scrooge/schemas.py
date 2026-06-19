from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    BUG_ANALYSIS = "bug_analysis"
    CODE_REVIEW = "code_review"
    REFACTORING = "refactoring"
    TEST_GENERATION = "test_generation"
    ARCHITECTURE_REVIEW = "architecture_review"
    LOG_ANALYSIS = "log_analysis"
    GENERAL = "general"


class UsageState(StrEnum):
    ESTIMATED = "estimated"
    SENT = "sent"
    MEASURED = "measured"
    REJECTED = "rejected"
    FAILED = "failed"


class TokenBreakdown(BaseModel):
    input_tokens: int
    output_tokens: int = 0
    tokenizer: str
    is_estimate: bool = True


class CostBreakdown(BaseModel):
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_version: str
    source_url: str
    is_estimate: bool = True


class OptimizeRequest(BaseModel):
    prompt: str = Field(min_length=1)
    provider: str = "openai"
    model: str = "gpt-5.4-mini"
    task_type: TaskType | None = None
    expected_output_tokens: int = Field(default=1000, ge=0, le=200000)


class OptimizationReason(BaseModel):
    rule_id: str
    description: str


class OptimizeResponse(BaseModel):
    request_id: str
    task_type: TaskType
    original_prompt: str
    optimized_prompt: str
    original_tokens: TokenBreakdown
    optimized_tokens: TokenBreakdown
    original_cost: CostBreakdown
    optimized_cost: CostBreakdown
    saved_tokens: int
    saved_cost_usd: float
    savings_rate: float
    reasons: list[OptimizationReason]
    created_at: datetime


class ApprovalRequest(BaseModel):
    approved: bool = True
    notes: str | None = None


class ApprovalResponse(BaseModel):
    request_id: str
    state: UsageState


class MeasurementRequest(BaseModel):
    measured_input_tokens: int = Field(ge=0)
    measured_output_tokens: int = Field(ge=0)
    measured_original_tokens: int | None = Field(default=None, ge=0)
    source: str = "provider_usage"


class MeasurementResponse(BaseModel):
    request_id: str
    state: UsageState
    estimated_input_tokens: int
    measured_input_tokens: int
    token_error_rate: float


class DashboardSummary(BaseModel):
    period: str
    total_requests: int
    approved_requests: int
    rejected_requests: int
    original_tokens: int
    optimized_tokens: int
    saved_tokens: int
    original_cost_usd: float
    optimized_cost_usd: float
    saved_cost_usd: float
    savings_rate: float
    measured_requests: int
    measurement_coverage: float = 0
    avg_token_error_rate: float = 0
    max_token_error_rate: float = 0


class AuditRecordSummary(BaseModel):
    request_id: str
    created_at: datetime
    provider: str
    model: str
    task_type: TaskType
    state: UsageState
    original_hash: str
    optimized_hash: str
    original_tokens: int
    optimized_tokens: int
    saved_tokens: int
    saved_cost_usd: float
    savings_rate: float
    pricing_version: str
    applied_rules: list[str]
    tokenizer_version: str
    measured_input_tokens: int | None = None
    measured_output_tokens: int | None = None
    measured_original_tokens: int | None = None
    token_error_rate: float | None = None


class ProxyCaptureResponse(BaseModel):
    request_id: str
    captured: bool
    forwarded: bool
    upstream_status: int | None = None
    preview: OptimizeResponse | None = None
    upstream_body: Any | None = None
