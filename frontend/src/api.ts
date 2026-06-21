import type {
  AuditRecordSummary,
  AdminPolicy,
  AttachmentMetadata,
  CategoryDashboardSummary,
  CompatibilityStatus,
  DashboardSummary,
  DiagnosticsBundle,
  MeasurementResponse,
  OptimizeResponse,
  QualitySummary,
  RuntimeStatus,
  SecurityScanResponse,
  TaskType
} from "./types";

const API_BASE = import.meta.env.VITE_SCROOGE_API_BASE ?? "http://127.0.0.1:8750";

export async function optimizePrompt(input: {
  prompt: string;
  provider: string;
  model: string;
  task_type?: TaskType | "";
  expected_output_tokens?: number;
  capture_source?: "manual" | "clipboard" | "hotkey" | "proxy";
  attachments?: AttachmentMetadata[];
}): Promise<OptimizeResponse> {
  const response = await fetch(`${API_BASE}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt: input.prompt,
      provider: input.provider,
      model: input.model,
      task_type: input.task_type || null,
      expected_output_tokens: input.expected_output_tokens ?? 1000,
      capture_source: input.capture_source ?? "manual",
      attachments: input.attachments ?? []
    })
  });
  if (!response.ok) {
    throw new Error(`Optimize failed: ${response.status}`);
  }
  return response.json();
}

export async function getDashboardCategorySummary(period = "month"): Promise<CategoryDashboardSummary[]> {
  const response = await fetch(`${API_BASE}/api/dashboard/category-summary?period=${period}`);
  if (!response.ok) {
    throw new Error(`Category dashboard failed: ${response.status}`);
  }
  return response.json();
}

export async function getRuntimeStatus(): Promise<RuntimeStatus> {
  const response = await fetch(`${API_BASE}/api/runtime/status`);
  if (!response.ok) {
    throw new Error(`Runtime status failed: ${response.status}`);
  }
  return response.json();
}

export async function getCompatibilityStatus(): Promise<CompatibilityStatus> {
  const response = await fetch(`${API_BASE}/api/compatibility/status`);
  if (!response.ok) {
    throw new Error(`Compatibility status failed: ${response.status}`);
  }
  return response.json();
}

export async function getAdminPolicy(): Promise<AdminPolicy> {
  const response = await fetch(`${API_BASE}/api/admin/policy`);
  if (!response.ok) {
    throw new Error(`Admin policy failed: ${response.status}`);
  }
  return response.json();
}

export async function getDiagnosticsBundle(): Promise<DiagnosticsBundle> {
  const response = await fetch(`${API_BASE}/api/diagnostics/bundle`);
  if (!response.ok) {
    throw new Error(`Diagnostics bundle failed: ${response.status}`);
  }
  return response.json();
}

export async function scanPromptSecurity(prompt: string): Promise<SecurityScanResponse> {
  const response = await fetch(`${API_BASE}/api/security/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt })
  });
  if (!response.ok) {
    throw new Error(`Security scan failed: ${response.status}`);
  }
  return response.json();
}

export async function approvePrompt(requestId: string, approved: boolean, notes?: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/approvals/${requestId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, notes: notes ?? null })
  });
  if (!response.ok) {
    throw new Error(`Approval failed: ${response.status}`);
  }
}

export async function getDashboardSummary(period = "month"): Promise<DashboardSummary> {
  const response = await fetch(`${API_BASE}/api/dashboard/summary?period=${period}`);
  if (!response.ok) {
    throw new Error(`Dashboard failed: ${response.status}`);
  }
  return response.json();
}

export async function getQualitySummary(): Promise<QualitySummary> {
  const response = await fetch(`${API_BASE}/api/quality/summary`);
  if (!response.ok) {
    throw new Error(`Quality summary failed: ${response.status}`);
  }
  return response.json();
}

export async function getAuditRecords(limit = 100): Promise<AuditRecordSummary[]> {
  const response = await fetch(`${API_BASE}/api/audit/records?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Audit records failed: ${response.status}`);
  }
  return response.json();
}

export async function clearAuditRecords(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/audit/records`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`Clear audit records failed: ${response.status}`);
  }
}

export async function recordMeasurement(input: {
  request_id: string;
  measured_input_tokens: number;
  measured_output_tokens: number;
  measured_original_tokens?: number;
  measured_total_input_tokens?: number;
  source?: string;
}): Promise<MeasurementResponse> {
  const response = await fetch(`${API_BASE}/api/audit/records/${input.request_id}/measurement`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      measured_input_tokens: input.measured_input_tokens,
      measured_output_tokens: input.measured_output_tokens,
      measured_original_tokens: input.measured_original_tokens ?? null,
      measured_total_input_tokens: input.measured_total_input_tokens ?? null,
      source: input.source ?? "provider_usage"
    })
  });
  if (!response.ok) {
    throw new Error(`Measurement failed: ${response.status}`);
  }
  return response.json();
}
