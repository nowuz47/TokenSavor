export type TaskType =
  | "bug_analysis"
  | "code_review"
  | "refactoring"
  | "test_generation"
  | "architecture_review"
  | "log_analysis"
  | "data_analysis"
  | "general";

export interface TokenBreakdown {
  input_tokens: number;
  output_tokens: number;
  tokenizer: string;
  is_estimate: boolean;
  tokenizer_confidence: "estimated_local" | "estimated_provider_count" | "heuristic_fallback" | "provider_measured";
}

export interface CostBreakdown {
  input_cost_usd: number;
  output_cost_usd: number;
  total_cost_usd: number;
  pricing_version: string;
  source_url: string;
  is_estimate: boolean;
}

export type AttachmentTokenStatus = "not_present" | "unknown" | "estimated" | "measured";
export type AttachmentDiscoverySource =
  | "scrooge_file"
  | "codex_uia"
  | "clipboard_file_drop"
  | "workspace_match"
  | "prompt_reference"
  | "proxy_payload"
  | "unknown";

export interface AttachmentMetadata {
  name: string;
  mime_type?: string | null;
  size_bytes?: number | null;
  content_hash?: string | null;
  content?: string | null;
  token_status: AttachmentTokenStatus;
  estimated_tokens?: number | null;
  measured_tokens?: number | null;
  original_tokens?: number | null;
  optimized_tokens?: number | null;
  saved_tokens?: number | null;
  savings_rate?: number | null;
  measurement_source?: string | null;
  discovery_source?: AttachmentDiscoverySource;
  content_available?: boolean;
  path_available?: boolean;
  read_error?: string | null;
}

export interface AttachmentSummary {
  attachment_count: number;
  token_status: AttachmentTokenStatus;
  possible_attachment_reference: boolean;
  prompt_original_tokens: number;
  prompt_optimized_tokens: number;
  prompt_saved_tokens: number;
  estimated_attachment_tokens?: number | null;
  measured_attachment_tokens?: number | null;
  attachment_original_tokens?: number | null;
  attachment_optimized_tokens?: number | null;
  attachment_saved_tokens?: number | null;
  attachment_savings_rate?: number | null;
  attachment_measurement_source?: string | null;
  total_original_tokens?: number | null;
  total_optimized_tokens?: number | null;
  total_saved_tokens?: number | null;
  prompt_savings_rate: number;
  total_savings_rate?: number | null;
  note: string;
}

export interface OptimizationReason {
  rule_id: string;
  description: string;
}

export interface OptimizeResponse {
  request_id: string;
  task_type: TaskType;
  original_prompt: string;
  optimized_prompt: string;
  original_tokens: TokenBreakdown;
  optimized_tokens: TokenBreakdown;
  original_cost: CostBreakdown;
  optimized_cost: CostBreakdown;
  saved_tokens: number;
  saved_cost_usd: number;
  savings_rate: number;
  prompt_savings_rate: number;
  total_savings_rate?: number | null;
  attachment_summary: AttachmentSummary;
  attachments: AttachmentMetadata[];
  optimization_mode: "token_savings" | "task_optimization";
  estimated_work_savings_minutes: number;
  estimated_followup_reduction: number;
  work_optimization_reason?: string | null;
  reasons: OptimizationReason[];
  created_at: string;
}

export interface DailySavingsTrendItem {
  date: string;
  total_requests: number;
  original_tokens: number;
  optimized_tokens: number;
  saved_tokens: number;
  saved_cost_usd: number;
  savings_rate: number;
}

export interface DashboardSummary {
  period: string;
  total_requests: number;
  approved_requests: number;
  rejected_requests: number;
  original_tokens: number;
  optimized_tokens: number;
  saved_tokens: number;
  original_cost_usd: number;
  optimized_cost_usd: number;
  saved_cost_usd: number;
  savings_rate: number;
  measured_requests: number;
  measurement_coverage: number;
  avg_token_error_rate: number;
  max_token_error_rate: number;
  followup_requests: number;
  reask_rate: number;
  quality_preservation_rate: number;
  long_context_savings_rate: number;
  short_prompt_over_optimization_count: number;
  short_prompt_protected_count: number;
  hotkey_attempts: number;
  hotkey_failed_requests: number;
  hotkey_success_rate: number;
  hotkey_validation_status: "needs_validation" | "passed" | "failed";
  latest_hotkey_status?: string | null;
  hotkey_discovered_attachments: number;
  hotkey_content_available_attachments: number;
  hotkey_unknown_attachments: number;
  hotkey_unsupported_attachments: number;
  used_assumed_requests: number;
  backend_health_status: string;
  attachment_requests: number;
  attachment_unknown_requests: number;
  attachment_measured_requests: number;
  attachment_measured_coverage: number;
  attachment_original_tokens: number;
  attachment_optimized_tokens: number;
  attachment_saved_tokens: number;
  attachment_savings_rate: number;
  daily_savings_trend: DailySavingsTrendItem[];
}

export interface QualityCategorySummary {
  category: string;
  total_cases: number;
  passed_cases: number;
  preservation_pass_rate: number;
  average_savings_rate: number;
  harmful_omission_count: number;
  hallucinated_constraint_count: number;
  over_optimization_count: number;
  savings_floor_failures: number;
}

export interface QualityCaseResult {
  name: string;
  category: string;
  passed: boolean;
  preservation_passed: boolean;
  behavior_passed: boolean;
  hallucination_passed: boolean;
  savings_passed: boolean;
  savings_rate: number;
  original_tokens: number;
  optimized_tokens: number;
  missing_terms: string[];
  missing_behaviors: string[];
  hallucinated_terms: string[];
  short_prompt: boolean;
  over_optimized: boolean;
}

export interface QualitySummary {
  total_cases: number;
  passed_cases: number;
  quality_preservation_rate: number;
  average_savings_rate: number;
  harmful_omission_count: number;
  hallucinated_constraint_count: number;
  over_optimization_count: number;
  category_summaries: QualityCategorySummary[];
  results: QualityCaseResult[];
}

export interface AuditRecordSummary {
  request_id: string;
  created_at: string;
  provider: string;
  model: string;
  task_type: TaskType;
  state: "estimated" | "sent" | "measured" | "rejected" | "failed";
  original_hash: string;
  optimized_hash: string;
  original_tokens: number;
  optimized_tokens: number;
  saved_tokens: number;
  saved_cost_usd: number;
  savings_rate: number;
  pricing_version: string;
  applied_rules: string[];
  tokenizer_version: string;
  measured_input_tokens?: number | null;
  measured_output_tokens?: number | null;
  measured_original_tokens?: number | null;
  rejection_reason?: string | null;
  provider_usage_source?: string | null;
  upstream_status?: number | null;
  capture_source: "manual" | "clipboard" | "hotkey" | "proxy";
  delivery_status:
    | "previewed"
    | "copied"
    | "pasted_assumed_used"
    | "sent_proxy"
    | "measured"
    | "not_used"
    | "failed";
  measurement_status: "estimated" | "measured" | "unavailable";
  failure_reason?: string | null;
  tokenizer_confidence: "estimated_local" | "estimated_provider_count" | "heuristic_fallback" | "provider_measured";
  token_error_rate?: number | null;
  attachment_count: number;
  attachment_token_status: AttachmentTokenStatus;
  attachment_estimated_tokens?: number | null;
  attachment_measured_tokens?: number | null;
  attachment_original_tokens?: number | null;
  attachment_optimized_tokens?: number | null;
  attachment_saved_tokens?: number | null;
  attachment_savings_rate?: number | null;
  attachment_measurement_source?: string | null;
  attachment_discovery_source?: string | null;
  attachment_content_available_count: number;
  attachment_path_available_count: number;
  attachment_read_error_count: number;
  possible_attachment_reference: boolean;
  prompt_savings_rate: number;
  total_savings_rate?: number | null;
  optimization_mode: "token_savings" | "task_optimization";
  estimated_work_savings_minutes: number;
  estimated_followup_reduction: number;
  work_optimization_reason?: string | null;
}

export interface CategoryDashboardSummary {
  category: string;
  total_requests: number;
  saved_tokens: number;
  savings_rate: number;
  measured_requests: number;
  avg_token_error_rate: number;
}

export interface RuntimeStatus {
  backend_status: string;
  database_status: string;
  hotkey_status: string;
  sidecar_status: string;
  database_path: string;
}

export interface CompatibilityTargetStatus {
  target_app: string;
  status: "pending_real_test" | "limited" | "verified" | "failed";
  attempts: number;
  successes: number;
  failures: number;
  success_rate: number;
  prompt_loss_count: number;
  required_attempts: number;
  last_verified_at?: string | null;
  failure_reasons: string[];
}

export interface CompatibilityStatus {
  overall_status: "pending_real_test" | "limited" | "verified" | "failed";
  targets: CompatibilityTargetStatus[];
}

export interface AdminPolicy {
  prompt_body_storage: string;
  telemetry_scope: string;
  hotkey_enabled: boolean;
  allowed_measurement_sources: string[];
  diagnostics_include_prompt_body: boolean;
  security_scan_required: boolean;
}

export interface SecurityFinding {
  kind: string;
  label: string;
  severity: "low" | "medium" | "high";
  start: number;
  end: number;
  preview: string;
}

export interface SecurityScanResponse {
  findings: SecurityFinding[];
  redacted_prompt: string;
  safe_to_store_body: boolean;
}

export interface DiagnosticsBundle {
  generated_at: string;
  app_version: string;
  prompt_body_included: boolean;
  runtime: RuntimeStatus;
  dashboard: DashboardSummary;
  compatibility: CompatibilityStatus;
  policy: AdminPolicy;
  recent_failures: Array<Record<string, unknown>>;
}

export interface MeasurementResponse {
  request_id: string;
  state: "measured";
  estimated_input_tokens: number;
  measured_input_tokens: number;
  token_error_rate: number;
}
