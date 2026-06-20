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
}

export interface CostBreakdown {
  input_cost_usd: number;
  output_cost_usd: number;
  total_cost_usd: number;
  pricing_version: string;
  source_url: string;
  is_estimate: boolean;
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
  reasons: OptimizationReason[];
  created_at: string;
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
  token_error_rate?: number | null;
}

export interface MeasurementResponse {
  request_id: string;
  state: "measured";
  estimated_input_tokens: number;
  measured_input_tokens: number;
  token_error_rate: number;
}
