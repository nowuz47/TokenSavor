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
    DATA_ANALYSIS = "data_analysis"
    GENERAL = "general"


class UsageState(StrEnum):
    ESTIMATED = "estimated"
    SENT = "sent"
    MEASURED = "measured"
    REJECTED = "rejected"
    FAILED = "failed"


class DeliveryStatus(StrEnum):
    PREVIEWED = "previewed"
    COPIED = "copied"
    PASTED_ASSUMED_USED = "pasted_assumed_used"
    SENT_PROXY = "sent_proxy"
    MEASURED = "measured"
    NOT_USED = "not_used"
    FAILED = "failed"


class MeasurementStatus(StrEnum):
    ESTIMATED = "estimated"
    MEASURED = "measured"
    UNAVAILABLE = "unavailable"


class CaptureSource(StrEnum):
    MANUAL = "manual"
    CLIPBOARD = "clipboard"
    HOTKEY = "hotkey"
    PROXY = "proxy"


class TokenizerConfidence(StrEnum):
    ESTIMATED_LOCAL = "estimated_local"
    ESTIMATED_PROVIDER_COUNT = "estimated_provider_count"
    HEURISTIC_FALLBACK = "heuristic_fallback"
    PROVIDER_MEASURED = "provider_measured"


class AttachmentTokenStatus(StrEnum):
    NOT_PRESENT = "not_present"
    UNKNOWN = "unknown"
    ESTIMATED = "estimated"
    MEASURED = "measured"


class AttachmentDiscoverySource(StrEnum):
    SCROOGE_FILE = "scrooge_file"
    CODEX_UIA = "codex_uia"
    CLIPBOARD_FILE_DROP = "clipboard_file_drop"
    WORKSPACE_MATCH = "workspace_match"
    PROMPT_REFERENCE = "prompt_reference"
    PROXY_PAYLOAD = "proxy_payload"
    UNKNOWN = "unknown"


class OptimizationMode(StrEnum):
    TOKEN_SAVINGS = "token_savings"
    TASK_OPTIMIZATION = "task_optimization"


class TokenBreakdown(BaseModel):
    input_tokens: int
    output_tokens: int = 0
    tokenizer: str
    is_estimate: bool = True
    tokenizer_confidence: TokenizerConfidence = TokenizerConfidence.HEURISTIC_FALLBACK


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
    capture_source: CaptureSource = CaptureSource.MANUAL
    attachments: list["AttachmentMetadata"] = Field(default_factory=list)


class AttachmentMetadata(BaseModel):
    name: str = Field(min_length=1)
    mime_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    content_hash: str | None = None
    content: str | None = Field(default=None, exclude=True)
    token_status: AttachmentTokenStatus = AttachmentTokenStatus.UNKNOWN
    estimated_tokens: int | None = Field(default=None, ge=0)
    measured_tokens: int | None = Field(default=None, ge=0)
    original_tokens: int | None = Field(default=None, ge=0)
    optimized_tokens: int | None = Field(default=None, ge=0)
    saved_tokens: int | None = Field(default=None, ge=0)
    savings_rate: float | None = Field(default=None, ge=0)
    measurement_source: str | None = None
    discovery_source: AttachmentDiscoverySource = AttachmentDiscoverySource.UNKNOWN
    content_available: bool = False
    path_available: bool = False
    read_error: str | None = None


class AttachmentSummary(BaseModel):
    attachment_count: int = 0
    token_status: AttachmentTokenStatus = AttachmentTokenStatus.NOT_PRESENT
    possible_attachment_reference: bool = False
    prompt_original_tokens: int = 0
    prompt_optimized_tokens: int = 0
    prompt_saved_tokens: int = 0
    estimated_attachment_tokens: int | None = None
    measured_attachment_tokens: int | None = None
    attachment_original_tokens: int | None = None
    attachment_optimized_tokens: int | None = None
    attachment_saved_tokens: int | None = None
    attachment_savings_rate: float | None = None
    attachment_measurement_source: str | None = None
    total_original_tokens: int | None = None
    total_optimized_tokens: int | None = None
    total_saved_tokens: int | None = None
    prompt_savings_rate: float = 0
    total_savings_rate: float | None = None
    note: str


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
    prompt_savings_rate: float
    total_savings_rate: float | None = None
    attachment_summary: AttachmentSummary
    attachments: list[AttachmentMetadata] = Field(default_factory=list)
    optimization_mode: OptimizationMode = OptimizationMode.TOKEN_SAVINGS
    estimated_work_savings_minutes: int = 0
    estimated_followup_reduction: float = 0
    work_optimization_reason: str | None = None
    reasons: list[OptimizationReason]
    created_at: datetime


class ApprovalRequest(BaseModel):
    approved: bool = True
    notes: str | None = None


class ApprovalResponse(BaseModel):
    request_id: str
    state: UsageState


class HotkeyEventRequest(BaseModel):
    request_id: str | None = None
    status: str
    failure_reason: str | None = None
    saved_tokens: int = Field(default=0, ge=0)
    elapsed_ms: int | None = Field(default=None, ge=0)
    discovered_attachment_count: int = Field(default=0, ge=0)
    content_available_attachment_count: int = Field(default=0, ge=0)
    unknown_attachment_count: int = Field(default=0, ge=0)
    unsupported_attachment_count: int = Field(default=0, ge=0)


class HotkeyEventResponse(BaseModel):
    event_id: str
    status: str


class MeasurementRequest(BaseModel):
    measured_input_tokens: int = Field(ge=0)
    measured_output_tokens: int = Field(ge=0)
    measured_original_tokens: int | None = Field(default=None, ge=0)
    measured_total_input_tokens: int | None = Field(default=None, ge=0)
    source: str = "provider_usage"
    upstream_status: int | None = None


class MeasurementResponse(BaseModel):
    request_id: str
    state: UsageState
    estimated_input_tokens: int
    measured_input_tokens: int
    token_error_rate: float


class DailySavingsTrendItem(BaseModel):
    date: str
    total_requests: int
    original_tokens: int
    optimized_tokens: int
    saved_tokens: int
    saved_cost_usd: float
    savings_rate: float


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
    followup_requests: int = 0
    reask_rate: float = 0
    quality_preservation_rate: float = 0
    long_context_savings_rate: float = 0
    task_optimization_requests: int = 0
    estimated_work_savings_minutes: int = 0
    average_followup_reduction: float = 0
    token_savings_requests: int = 0
    zero_token_task_optimizations: int = 0
    short_prompt_over_optimization_count: int = 0
    short_prompt_protected_count: int = 0
    hotkey_attempts: int = 0
    hotkey_failed_requests: int = 0
    hotkey_success_rate: float = 0
    hotkey_validation_status: str = "needs_validation"
    latest_hotkey_status: str | None = None
    hotkey_discovered_attachments: int = 0
    hotkey_content_available_attachments: int = 0
    hotkey_unknown_attachments: int = 0
    hotkey_unsupported_attachments: int = 0
    used_assumed_requests: int = 0
    backend_health_status: str = "ok"
    attachment_requests: int = 0
    attachment_unknown_requests: int = 0
    attachment_measured_requests: int = 0
    attachment_measured_coverage: float = 0
    attachment_original_tokens: int = 0
    attachment_optimized_tokens: int = 0
    attachment_saved_tokens: int = 0
    attachment_savings_rate: float = 0
    daily_savings_trend: list[DailySavingsTrendItem] = Field(default_factory=list)


class QualityCaseResult(BaseModel):
    name: str
    category: str
    passed: bool
    preservation_passed: bool
    behavior_passed: bool
    hallucination_passed: bool
    savings_passed: bool
    savings_rate: float
    original_tokens: int
    optimized_tokens: int
    missing_terms: list[str]
    missing_behaviors: list[str]
    hallucinated_terms: list[str]
    short_prompt: bool
    over_optimized: bool


class QualityCategorySummary(BaseModel):
    category: str
    total_cases: int
    passed_cases: int
    preservation_pass_rate: float
    average_savings_rate: float
    harmful_omission_count: int
    hallucinated_constraint_count: int
    over_optimization_count: int
    savings_floor_failures: int


class QualitySummary(BaseModel):
    total_cases: int
    passed_cases: int
    quality_preservation_rate: float
    average_savings_rate: float
    harmful_omission_count: int
    hallucinated_constraint_count: int
    over_optimization_count: int
    category_summaries: list[QualityCategorySummary]
    results: list[QualityCaseResult]


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
    rejection_reason: str | None = None
    provider_usage_source: str | None = None
    upstream_status: int | None = None
    capture_source: CaptureSource = CaptureSource.MANUAL
    delivery_status: DeliveryStatus = DeliveryStatus.PREVIEWED
    measurement_status: MeasurementStatus = MeasurementStatus.ESTIMATED
    failure_reason: str | None = None
    tokenizer_confidence: TokenizerConfidence = TokenizerConfidence.HEURISTIC_FALLBACK
    token_error_rate: float | None = None
    attachment_count: int = 0
    attachment_token_status: AttachmentTokenStatus = AttachmentTokenStatus.NOT_PRESENT
    attachment_estimated_tokens: int | None = None
    attachment_measured_tokens: int | None = None
    attachment_original_tokens: int | None = None
    attachment_optimized_tokens: int | None = None
    attachment_saved_tokens: int | None = None
    attachment_savings_rate: float | None = None
    attachment_measurement_source: str | None = None
    attachment_discovery_source: str | None = None
    attachment_content_available_count: int = 0
    attachment_path_available_count: int = 0
    attachment_read_error_count: int = 0
    possible_attachment_reference: bool = False
    prompt_savings_rate: float = 0
    total_savings_rate: float | None = None
    optimization_mode: OptimizationMode = OptimizationMode.TOKEN_SAVINGS
    estimated_work_savings_minutes: int = 0
    estimated_followup_reduction: float = 0
    work_optimization_reason: str | None = None


class RuntimeStatusResponse(BaseModel):
    backend_status: str
    database_status: str
    hotkey_status: str = "unknown"
    sidecar_status: str = "unknown"
    database_path: str


class CompatibilityRunRequest(BaseModel):
    target_app: str = "codex_desktop"
    target_version: str | None = None
    verification_mode: str = "user_assisted_real_input"
    attempts: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    prompt_loss_count: int = Field(default=0, ge=0)
    failure_reasons: list[str] = Field(default_factory=list)
    notes: str | None = None


class CompatibilityRunResponse(BaseModel):
    run_id: str
    target_app: str
    status: str
    attempts: int
    successes: int
    failures: int
    success_rate: float
    prompt_loss_count: int
    verified_at: datetime


class CompatibilityTargetStatus(BaseModel):
    target_app: str
    status: str
    attempts: int
    successes: int
    failures: int
    success_rate: float
    prompt_loss_count: int
    required_attempts: int = 100
    last_verified_at: datetime | None = None
    failure_reasons: list[str] = Field(default_factory=list)


class CompatibilityStatusResponse(BaseModel):
    overall_status: str
    targets: list[CompatibilityTargetStatus]


class SecurityScanRequest(BaseModel):
    prompt: str


class SecurityFinding(BaseModel):
    kind: str
    label: str
    severity: str
    start: int
    end: int
    preview: str


class SecurityScanResponse(BaseModel):
    findings: list[SecurityFinding]
    redacted_prompt: str
    safe_to_store_body: bool


class AdminPolicyResponse(BaseModel):
    prompt_body_storage: str
    telemetry_scope: str
    hotkey_enabled: bool
    allowed_measurement_sources: list[str]
    diagnostics_include_prompt_body: bool
    security_scan_required: bool


class DiagnosticsBundleResponse(BaseModel):
    generated_at: datetime
    app_version: str
    prompt_body_included: bool
    runtime: RuntimeStatusResponse
    dashboard: DashboardSummary
    compatibility: CompatibilityStatusResponse
    policy: AdminPolicyResponse
    recent_failures: list[dict[str, Any]]


class CategoryDashboardSummary(BaseModel):
    category: str
    total_requests: int
    saved_tokens: int
    savings_rate: float
    measured_requests: int
    avg_token_error_rate: float
    task_optimization_requests: int = 0
    token_savings_requests: int = 0


class ProxyCaptureResponse(BaseModel):
    request_id: str
    captured: bool
    forwarded: bool
    optimized_forwarded: bool = False
    upstream_status: int | None = None
    preview: OptimizeResponse | None = None
    upstream_body: Any | None = None
