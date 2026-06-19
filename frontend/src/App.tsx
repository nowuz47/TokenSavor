import { BarChart3, Check, ClipboardCheck, Gauge, RefreshCw, ShieldCheck, X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { approvePrompt, getDashboardSummary, optimizePrompt } from "./api";
import type { DashboardSummary, OptimizeResponse, TaskType } from "./types";

const taskOptions: Array<{ label: string; value: TaskType | "" }> = [
  { label: "Auto", value: "" },
  { label: "Bug", value: "bug_analysis" },
  { label: "Review", value: "code_review" },
  { label: "Refactor", value: "refactoring" },
  { label: "Test", value: "test_generation" },
  { label: "Logs", value: "log_analysis" }
];

export default function App() {
  const [prompt, setPrompt] = useState(
    "이 코드가 이상한 것 같은데 한번 확인해 주세요\n\nERROR failed to parse config\nERROR failed to parse config"
  );
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-5.4-mini");
  const [taskType, setTaskType] = useState<TaskType | "">("");
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [status, setStatus] = useState("Ready");
  const [loading, setLoading] = useState(false);

  const savingsPercent = useMemo(() => {
    if (!result) return "0.0";
    return (result.savings_rate * 100).toFixed(1);
  }, [result]);

  async function refreshSummary() {
    try {
      setSummary(await getDashboardSummary("month"));
    } catch {
      setSummary(null);
    }
  }

  async function runOptimize() {
    setLoading(true);
    setStatus("Optimizing");
    try {
      const response = await optimizePrompt({ prompt, provider, model, task_type: taskType });
      setResult(response);
      setStatus("Preview ready");
      await refreshSummary();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Optimize failed");
    } finally {
      setLoading(false);
    }
  }

  async function decide(approved: boolean) {
    if (!result) return;
    setLoading(true);
    try {
      await approvePrompt(result.request_id, approved);
      setStatus(approved ? "Approved as sent" : "Rejected");
      await refreshSummary();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Approval failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshSummary();
  }, []);

  return (
    <main className="app-shell">
      <section className="toolbar" aria-label="Scrooge controls">
        <div>
          <h1>Scrooge</h1>
          <p>Local prompt optimization, token metering, and cost audit.</p>
        </div>
        <div className="status-pill">
          <ShieldCheck size={16} />
          <span>{status}</span>
        </div>
      </section>

      <section className="metrics-band" aria-label="Efficiency dashboard">
        <Metric icon={<Gauge size={18} />} label="Saved Tokens" value={summary?.saved_tokens ?? 0} />
        <Metric
          icon={<BarChart3 size={18} />}
          label="Savings Rate"
          value={`${((summary?.savings_rate ?? 0) * 100).toFixed(1)}%`}
        />
        <Metric
          icon={<ClipboardCheck size={18} />}
          label="Approved"
          value={summary?.approved_requests ?? 0}
        />
        <Metric label="Estimated USD" value={`$${(summary?.saved_cost_usd ?? 0).toFixed(4)}`} />
      </section>

      <section className="workspace">
        <div className="editor-pane">
          <div className="pane-header">
            <h2>Original Prompt</h2>
            <button className="icon-button" onClick={runOptimize} disabled={loading || !prompt.trim()}>
              <RefreshCw size={17} />
              <span>Optimize</span>
            </button>
          </div>

          <div className="controls-grid">
            <label>
              Provider
              <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Gemini</option>
              </select>
            </label>
            <label>
              Model
              <input value={model} onChange={(event) => setModel(event.target.value)} />
            </label>
          </div>

          <div className="segmented" aria-label="Task type">
            {taskOptions.map((option) => (
              <button
                key={option.label}
                className={taskType === option.value ? "selected" : ""}
                onClick={() => setTaskType(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>

          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
        </div>

        <div className="preview-pane">
          <div className="pane-header">
            <h2>Optimization Preview</h2>
            <div className="decision-actions">
              <button className="icon-button approve" onClick={() => decide(true)} disabled={!result || loading}>
                <Check size={17} />
                <span>Approve</span>
              </button>
              <button className="icon-button reject" onClick={() => decide(false)} disabled={!result || loading}>
                <X size={17} />
                <span>Reject</span>
              </button>
            </div>
          </div>

          {result ? (
            <>
              <div className="token-strip">
                <span>{result.original_tokens.input_tokens.toLocaleString()} original</span>
                <span>{result.optimized_tokens.input_tokens.toLocaleString()} optimized</span>
                <strong>{savingsPercent}% saved</strong>
              </div>
              <textarea value={result.optimized_prompt} readOnly />
              <div className="reason-list">
                {result.reasons.map((reason) => (
                  <span key={`${reason.rule_id}-${reason.description}`}>{reason.description}</span>
                ))}
              </div>
              <p className="pricing-note">
                Pricing: {result.optimized_cost.pricing_version} · estimated savings $
                {result.saved_cost_usd.toFixed(6)}
              </p>
            </>
          ) : (
            <div className="empty-preview">
              <Gauge size={28} />
              <p>Run optimization to review token and cost impact before sending.</p>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function Metric(props: { icon?: ReactNode; label: string; value: string | number }) {
  return (
    <div className="metric">
      <div className="metric-icon">{props.icon}</div>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}
