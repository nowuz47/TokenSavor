import type {
  AuditRecordSummary,
  DashboardSummary,
  MeasurementResponse,
  OptimizeResponse,
  TaskType
} from "./types";

const API_BASE = import.meta.env.VITE_SCROOGE_API_BASE ?? "http://127.0.0.1:8750";

export async function optimizePrompt(input: {
  prompt: string;
  provider: string;
  model: string;
  task_type?: TaskType | "";
  expected_output_tokens?: number;
}): Promise<OptimizeResponse> {
  const response = await fetch(`${API_BASE}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt: input.prompt,
      provider: input.provider,
      model: input.model,
      task_type: input.task_type || null,
      expected_output_tokens: input.expected_output_tokens ?? 1000
    })
  });
  if (!response.ok) {
    throw new Error(`Optimize failed: ${response.status}`);
  }
  return response.json();
}

export async function approvePrompt(requestId: string, approved: boolean): Promise<void> {
  const response = await fetch(`${API_BASE}/api/approvals/${requestId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved })
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
  source?: string;
}): Promise<MeasurementResponse> {
  const response = await fetch(`${API_BASE}/api/audit/records/${input.request_id}/measurement`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      measured_input_tokens: input.measured_input_tokens,
      measured_output_tokens: input.measured_output_tokens,
      measured_original_tokens: input.measured_original_tokens ?? null,
      source: input.source ?? "provider_usage"
    })
  });
  if (!response.ok) {
    throw new Error(`Measurement failed: ${response.status}`);
  }
  return response.json();
}
