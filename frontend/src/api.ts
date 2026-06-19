import type { DashboardSummary, OptimizeResponse, TaskType } from "./types";

const API_BASE = import.meta.env.VITE_SCROOGE_API_BASE ?? "http://127.0.0.1:8750";

export async function optimizePrompt(input: {
  prompt: string;
  provider: string;
  model: string;
  task_type?: TaskType | "";
}): Promise<OptimizeResponse> {
  const response = await fetch(`${API_BASE}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt: input.prompt,
      provider: input.provider,
      model: input.model,
      task_type: input.task_type || null
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

