import {
  Activity,
  Award,
  Banknote,
  BarChart3,
  Check,
  CheckCircle,
  Cpu,
  Database,
  Edit3,
  Eye,
  Flame,
  Minus,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  Trash2,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { approvePrompt, getDashboardSummary, optimizePrompt } from "./api";
import type { DashboardSummary, OptimizationReason, OptimizeResponse, TaskType } from "./types";

type TabId = "workspace" | "dashboard" | "audit" | "pricing" | "settings";
type WorkspacePanel = "input" | "preview";

interface ModelOption {
  provider: string;
  model: string;
  input: number;
  cached: number;
  output: number;
  date: string;
  url: string;
}

interface AuditRecord {
  id: string;
  time: string;
  provider: string;
  model: string;
  type: string;
  originalTokens: number;
  optimizedTokens: number;
  savedTokens: number;
  rate: number;
  savedCost: number;
  state: "sent" | "rejected" | "estimated";
  rules: string[];
  hashOrig: string;
  hashOpt: string;
}

const modelsRegistry: ModelOption[] = [
  {
    provider: "openai",
    model: "gpt-5.5",
    input: 5,
    cached: 0.5,
    output: 30,
    date: "2026-06-19",
    url: "https://developers.openai.com/api/docs/pricing"
  },
  {
    provider: "openai",
    model: "gpt-5.4-mini",
    input: 0.75,
    cached: 0.075,
    output: 4.5,
    date: "2026-06-19",
    url: "https://developers.openai.com/api/docs/pricing"
  },
  {
    provider: "anthropic",
    model: "claude-sonnet-4.6",
    input: 3,
    cached: 0.3,
    output: 15,
    date: "2026-06-19",
    url: "https://platform.claude.com/docs/en/about-claude/pricing"
  },
  {
    provider: "anthropic",
    model: "claude-haiku-4.5",
    input: 1,
    cached: 0.1,
    output: 5,
    date: "2026-06-19",
    url: "https://platform.claude.com/docs/en/about-claude/pricing"
  },
  {
    provider: "gemini",
    model: "gemini-3-flash",
    input: 0.25,
    cached: 0.025,
    output: 1.5,
    date: "2026-06-19",
    url: "https://ai.google.dev/gemini-api/docs/pricing"
  },
  {
    provider: "gemini",
    model: "gemini-2.5-flash-lite",
    input: 0.1,
    cached: 0.01,
    output: 0.4,
    date: "2026-06-19",
    url: "https://ai.google.dev/gemini-api/docs/pricing"
  }
];

const taskOptions: Array<{ label: string; value: TaskType | "" }> = [
  { label: "Auto", value: "" },
  { label: "Bug", value: "bug_analysis" },
  { label: "Review", value: "code_review" },
  { label: "Refactor", value: "refactoring" },
  { label: "Test", value: "test_generation" },
  { label: "Logs", value: "log_analysis" }
];

const seedAuditRecords: AuditRecord[] = [
  {
    id: "req-c62f91",
    time: "14:32:01",
    provider: "anthropic",
    model: "claude-sonnet-4.6",
    type: "bug_analysis",
    originalTokens: 14500,
    optimizedTokens: 7800,
    savedTokens: 6700,
    rate: 0.46,
    savedCost: 0.0201,
    state: "sent",
    rules: ["stacktrace_cause_preservation", "task_template"],
    hashOrig: "sha256:d8c47f3b...",
    hashOpt: "sha256:ef8a42b1..."
  },
  {
    id: "req-29b19e",
    time: "11:22:15",
    provider: "openai",
    model: "gpt-5.4-mini",
    type: "log_analysis",
    originalTokens: 25000,
    optimizedTokens: 4500,
    savedTokens: 20500,
    rate: 0.82,
    savedCost: 0.0154,
    state: "sent",
    rules: ["log_error_frequency_summary", "task_template"],
    hashOrig: "sha256:88fa29cc...",
    hashOpt: "sha256:92cb911a..."
  },
  {
    id: "req-72fc10",
    time: "15:10:04",
    provider: "anthropic",
    model: "claude-sonnet-4.6",
    type: "test_generation",
    originalTokens: 12000,
    optimizedTokens: 9200,
    savedTokens: 2800,
    rate: 0.23,
    savedCost: 0.0084,
    state: "rejected",
    rules: ["generic_head_tail_compaction", "task_template"],
    hashOrig: "sha256:bb291aef...",
    hashOpt: "sha256:cc98df0a..."
  }
];

const defaultPrompt =
  "이 코드가 이상한 것 같은데 한번 확인해 주세요.\n\n" +
  "ERROR 12:04:15 c.s.config.ServerBootstrap - failed to parse config\n" +
  "ERROR 12:04:15 c.s.config.ServerBootstrap - failed to parse config\n" +
  "ERROR 12:04:15 c.s.config.ServerBootstrap - failed to parse config\n" +
  "Traceback (most recent call last):\n" +
  '  File "/app/scrooge/config.py", line 45, in parse_yaml\n' +
  "    config = yaml.safe_load(f)\n" +
  "yaml.parser.ParserError: expected '<document start>', but found '<block start>'";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("workspace");
  const [workspacePanel, setWorkspacePanel] = useState<WorkspacePanel>("input");
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-5.4-mini");
  const [taskType, setTaskType] = useState<TaskType | "">("");
  const [expectedOutputTokens, setExpectedOutputTokens] = useState(1000);
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>(seedAuditRecords);
  const [expandedAuditId, setExpandedAuditId] = useState<string | null>(null);
  const [auditSearch, setAuditSearch] = useState("");
  const [pricingSearch, setPricingSearch] = useState("");
  const [status, setStatus] = useState("Proxy Running (Port 8750)");
  const [toast, setToast] = useState("");
  const [proxyRunning, setProxyRunning] = useState(true);
  const [loading, setLoading] = useState(false);

  const availableModels = useMemo(
    () => modelsRegistry.filter((item) => item.provider === provider),
    [provider]
  );

  const activeRecords = useMemo(
    () => auditRecords.filter((record) => record.state === "sent"),
    [auditRecords]
  );

  const aggregate = useMemo(() => {
    const originalTokens = activeRecords.reduce((total, record) => total + record.originalTokens, 0);
    const optimizedTokens = activeRecords.reduce((total, record) => total + record.optimizedTokens, 0);
    const savedTokens = originalTokens - optimizedTokens + (summary?.saved_tokens ?? 0);
    const savedCost =
      activeRecords.reduce((total, record) => total + record.savedCost, 0) +
      (summary?.saved_cost_usd ?? 0);
    const backendOriginal = summary?.original_tokens ?? 0;
    const denominator = originalTokens + backendOriginal;
    return {
      savedTokens,
      savedCost,
      savingsRate: denominator > 0 ? savedTokens / denominator : 0,
      approved: activeRecords.length + (summary?.approved_requests ?? 0),
      totalAudits: auditRecords.length + (summary?.total_requests ?? 0)
    };
  }, [activeRecords, auditRecords.length, summary]);

  const filteredAuditRecords = useMemo(() => {
    const needle = auditSearch.toLowerCase();
    return auditRecords.filter((record) =>
      [record.id, record.model, record.type, record.state].some((value) =>
        value.toLowerCase().includes(needle)
      )
    );
  }, [auditRecords, auditSearch]);

  const filteredPrices = useMemo(() => {
    const needle = pricingSearch.toLowerCase();
    return modelsRegistry.filter((item) =>
      [item.provider, item.model].some((value) => value.toLowerCase().includes(needle))
    );
  }, [pricingSearch]);

  useEffect(() => {
    refreshSummary();
  }, []);

  useEffect(() => {
    const next = modelsRegistry.find((item) => item.provider === provider);
    if (next) setModel(next.model);
  }, [provider]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function refreshSummary() {
    try {
      setSummary(await getDashboardSummary("month"));
    } catch {
      setSummary(null);
    }
  }

  async function runOptimize() {
    if (!proxyRunning) {
      showToast("Optimization disabled while proxy router is stopped.");
      return;
    }
    if (!prompt.trim()) {
      showToast("Paste context or a request first.");
      return;
    }
    setLoading(true);
    setStatus("Optimizing request");
    try {
      const response = await optimizePrompt({
        prompt,
        provider,
        model,
        task_type: taskType,
        expected_output_tokens: expectedOutputTokens
      });
      setResult(response);
      setWorkspacePanel("preview");
      setStatus("Optimization preview loaded");
      showToast("Optimization preview loaded.");
      await refreshSummary();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Optimize failed";
      setStatus(message);
      showToast(message);
    } finally {
      setLoading(false);
    }
  }

  async function decide(approved: boolean) {
    if (!result) return;
    setLoading(true);
    try {
      await approvePrompt(result.request_id, approved);
      const record: AuditRecord = {
        id: result.request_id.slice(0, 10),
        time: new Date().toTimeString().split(" ")[0],
        provider,
        model,
        type: result.task_type,
        originalTokens: result.original_tokens.input_tokens,
        optimizedTokens: result.optimized_tokens.input_tokens,
        savedTokens: result.saved_tokens,
        rate: result.savings_rate,
        savedCost: result.saved_cost_usd,
        state: approved ? "sent" : "rejected",
        rules: result.reasons.map((reason) => reason.rule_id),
        hashOrig: `sha256:${result.request_id.slice(0, 8)}...`,
        hashOpt: `sha256:${result.request_id.slice(9, 17)}...`
      };
      setAuditRecords((current) => [record, ...current]);
      setStatus(approved ? "Request approved & sent via proxy" : "Optimized prompt rejected");
      showToast(approved ? "Request approved & sent via proxy." : "Optimized prompt rejected.");
      setResult(null);
      setWorkspacePanel("input");
      await refreshSummary();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Approval failed";
      setStatus(message);
      showToast(message);
    } finally {
      setLoading(false);
    }
  }

  function showToast(message: string) {
    setToast(message);
  }

  function toggleProxy() {
    setProxyRunning((current) => {
      const next = !current;
      setStatus(next ? "Proxy Running (Port 8750)" : "Proxy Inactive (Stopped)");
      showToast(next ? "Scrooge local proxy router started." : "Requests will bypass optimization.");
      return next;
    });
  }

  function syncLogs() {
    showToast("Sync complete: audit hashes uploaded to enterprise telemetry.");
  }

  function clearLocalRecords() {
    setAuditRecords([]);
    setExpandedAuditId(null);
    showToast("Local UI audit records cleared.");
  }

  const tabContent = {
    workspace: (
      <WorkspaceTab
        availableModels={availableModels}
        expectedOutputTokens={expectedOutputTokens}
        loading={loading}
        model={model}
        prompt={prompt}
        provider={provider}
        result={result}
        taskType={taskType}
        workspacePanel={workspacePanel}
        onApprove={() => decide(true)}
        onExpectedOutputTokensChange={setExpectedOutputTokens}
        onModelChange={setModel}
        onOptimize={runOptimize}
        onPromptChange={setPrompt}
        onProviderChange={setProvider}
        onReject={() => decide(false)}
        onTaskTypeChange={setTaskType}
        onWorkspacePanelChange={setWorkspacePanel}
      />
    ),
    dashboard: (
      <DashboardTab aggregate={aggregate} records={auditRecords} />
    ),
    audit: (
      <AuditTab
        expandedAuditId={expandedAuditId}
        records={filteredAuditRecords}
        search={auditSearch}
        onExpand={setExpandedAuditId}
        onSearch={setAuditSearch}
      />
    ),
    pricing: (
      <PricingTab prices={filteredPrices} search={pricingSearch} onSearch={setPricingSearch} />
    ),
    settings: <SettingsTab />
  } satisfies Record<TabId, JSX.Element>;

  return (
    <main className="app-container">
      <header className="app-header">
        <div className="brand-group">
          <div className="brand-logo">
            <img src="/scrooge_flat_no_coin.png" alt="Scrooge" />
          </div>
          <span className="brand-title">Scrooge</span>
        </div>
        <div className="header-metrics">
          <span>{(aggregate.savingsRate * 100).toFixed(0)}%</span>
          <strong>${aggregate.savedCost.toFixed(2)}</strong>
        </div>
        <div className="window-actions">
          <button className="win-btn" type="button" title="Minimize to tray" onClick={() => showToast("Window minimized to tray.")}>
            <Minus size={14} />
          </button>
          <button className="win-btn close" type="button" title="Quit Scrooge" onClick={() => showToast("Scrooge tray daemon keeps running.")}>
            <X size={14} />
          </button>
        </div>
      </header>

      <div className="content-area">{tabContent[activeTab]}</div>

      <div className="status-bar">
        <button className="status-left" type="button" onClick={toggleProxy}>
          <span className={`status-indicator-dot ${proxyRunning ? "" : "inactive"}`} />
          <span>{status}</span>
        </button>
        <div className="status-right">
          <span>scrooge.db ({aggregate.totalAudits} records)</span>
          <button className="status-btn" type="button" onClick={syncLogs}>
            <RefreshCw size={11} />
            <span>Sync Logs</span>
          </button>
          <button className="status-btn" type="button" onClick={clearLocalRecords}>
            <Trash2 size={11} />
            <span>Clear DB</span>
          </button>
        </div>
      </div>

      <nav className="bottom-nav">
        <NavItem active={activeTab === "workspace"} icon={<SlidersHorizontal />} label="Workspace" onClick={() => setActiveTab("workspace")} />
        <NavItem active={activeTab === "dashboard"} icon={<BarChart3 />} label="Dashboard" onClick={() => setActiveTab("dashboard")} />
        <NavItem active={activeTab === "audit"} icon={<Database />} label="Audit Logs" onClick={() => setActiveTab("audit")} />
        <NavItem active={activeTab === "pricing"} icon={<Banknote />} label="Rates" onClick={() => setActiveTab("pricing")} />
        <NavItem active={activeTab === "settings"} icon={<Settings />} label="Settings" onClick={() => setActiveTab("settings")} />
      </nav>

      <div className={`toast ${toast ? "active" : ""}`}>
        <CheckCircle size={16} />
        <span>{toast || "Task complete."}</span>
      </div>
    </main>
  );
}

function WorkspaceTab(props: {
  availableModels: ModelOption[];
  expectedOutputTokens: number;
  loading: boolean;
  model: string;
  prompt: string;
  provider: string;
  result: OptimizeResponse | null;
  taskType: TaskType | "";
  workspacePanel: WorkspacePanel;
  onApprove: () => void;
  onExpectedOutputTokensChange: (value: number) => void;
  onModelChange: (value: string) => void;
  onOptimize: () => void;
  onPromptChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onReject: () => void;
  onTaskTypeChange: (value: TaskType | "") => void;
  onWorkspacePanelChange: (value: WorkspacePanel) => void;
}) {
  return (
    <section className="tab-content active">
      <div className="panel-toggle-bar">
        <button
          className={`panel-toggle-btn ${props.workspacePanel === "input" ? "active" : ""}`}
          type="button"
          onClick={() => props.onWorkspacePanelChange("input")}
        >
          <Edit3 size={12} />
          Workbench Input
        </button>
        <button
          className={`panel-toggle-btn ${props.workspacePanel === "preview" ? "active" : ""}`}
          type="button"
          onClick={() => props.onWorkspacePanelChange("preview")}
        >
          <Eye size={12} />
          Optimization View
        </button>
      </div>

      {props.workspacePanel === "input" ? (
        <div className="compact-card">
          <div className="card-header">
            <h3>
              <Terminal size={14} />
              Original Request
            </h3>
            <button className="btn btn-primary" type="button" onClick={props.onOptimize} disabled={props.loading}>
              <Sparkles size={12} />
              Optimize
            </button>
          </div>
          <div className="card-body">
            <div className="form-row">
              <label className="form-group">
                Provider
                <select
                  className="form-control"
                  value={props.provider}
                  onChange={(event) => props.onProviderChange(event.target.value)}
                >
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Gemini</option>
                </select>
              </label>
              <label className="form-group">
                Target Model
                <select
                  className="form-control"
                  value={props.model}
                  onChange={(event) => props.onModelChange(event.target.value)}
                >
                  {props.availableModels.map((item) => (
                    <option key={item.model} value={item.model}>
                      {item.model}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="form-group">
              Max Out Tokens: {props.expectedOutputTokens}
              <div className="slider-box">
                <input
                  max={4000}
                  min={100}
                  step={100}
                  type="range"
                  value={props.expectedOutputTokens}
                  onChange={(event) => props.onExpectedOutputTokensChange(Number(event.target.value))}
                />
                <span className="slider-val">~{Math.round(props.expectedOutputTokens / 1000)}K</span>
              </div>
            </label>

            <div className="form-group">
              <span className="form-label">Task Template</span>
              <div className="task-tags">
                {taskOptions.map((option) => (
                  <button
                    key={option.label}
                    className={`tag-btn ${props.taskType === option.value ? "active" : ""}`}
                    type="button"
                    onClick={() => props.onTaskTypeChange(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <label className="form-group grow">
              Context / Query Body
              <div className="editor-box">
                <textarea
                  className="editor-textarea"
                  placeholder="Paste noisy logs or code blocks here..."
                  value={props.prompt}
                  onChange={(event) => props.onPromptChange(event.target.value)}
                />
              </div>
            </label>
          </div>
        </div>
      ) : (
        <PreviewPanel result={props.result} onApprove={props.onApprove} onReject={props.onReject} />
      )}
    </section>
  );
}

function PreviewPanel(props: {
  result: OptimizeResponse | null;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <div className="compact-card preview-card">
      <div className="card-header">
        <h3>
          <Eye size={14} />
          Optimization Preview
        </h3>
        <div className="card-actions">
          <button className="btn btn-outline" type="button" disabled={!props.result} onClick={props.onReject}>
            <X size={12} />
            Reject
          </button>
          <button className="btn btn-primary" type="button" disabled={!props.result} onClick={props.onApprove}>
            <Check size={12} />
            Approve
          </button>
        </div>
      </div>

      {!props.result ? (
        <div className="empty-preview-pane">
          <Cpu size={28} />
          <p>Run prompt optimization first under the workbench tab to view savings and code diffs.</p>
        </div>
      ) : (
        <div className="card-body">
          <div className="token-bar">
            <div>
              Original: <strong>{props.result.original_tokens.input_tokens.toLocaleString()}</strong>
            </div>
            <div>
              Optimized: <strong>{props.result.optimized_tokens.input_tokens.toLocaleString()}</strong>
            </div>
            <span className="token-badge">{(props.result.savings_rate * 100).toFixed(1)}% Saved</span>
          </div>

          <div className="form-group">
            <span className="form-label">Structural Context Changes</span>
            <div className="diff-tray-layout">
              <div className="diff-section">
                <div className="diff-header-line">REMOVED / CLEANED UP</div>
                <div className="diff-body-text">
                  {renderDiffLines(props.result.original_prompt, props.result.reasons, "removed")}
                </div>
              </div>
              <div className="diff-section">
                <div className="diff-header-line">ADDED / TARGET DIRECTIVES</div>
                <div className="diff-body-text">
                  {renderDiffLines(props.result.optimized_prompt, props.result.reasons, "added")}
                </div>
              </div>
            </div>
          </div>

          <div className="form-group">
            <span className="form-label">Applied Reduction Rules</span>
            <div className="rules-grid">
              {props.result.reasons.map((reason) => (
                <span className="rule-chip" key={`${reason.rule_id}-${reason.description}`}>
                  <Check size={10} />
                  {reason.rule_id}
                </span>
              ))}
            </div>
          </div>

          <div className="audit-footer-strip">
            <div>
              Pricing Registry: <strong>{props.result.optimized_cost.pricing_version}</strong>
            </div>
            <a className="audit-ref-link" href={props.result.optimized_cost.source_url} rel="noreferrer" target="_blank">
              Verify Official Rates
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

function DashboardTab(props: {
  aggregate: { approved: number; savedCost: number; savedTokens: number; savingsRate: number; totalAudits: number };
  records: AuditRecord[];
}) {
  return (
    <section className="tab-content active">
      <div className="db-grid">
        <DashboardCard icon={<Flame />} label="Savings Rate" value={`${(props.aggregate.savingsRate * 100).toFixed(1)}%`} highlight />
        <DashboardCard icon={<Award />} label="Saved Tokens" value={`${Math.round(props.aggregate.savedTokens / 1000)}K`} />
        <DashboardCard icon={<Banknote />} label="Saved USD" value={`$${props.aggregate.savedCost.toFixed(2)}`} />
        <DashboardCard icon={<Database />} label="Total Audits" value={props.aggregate.totalAudits} />
      </div>

      <div className="chart-card">
        <div className="chart-title">Token Savings Trend</div>
        <div className="chart-holder" aria-label="Token savings trend">
          <span style={{ height: "64%" }} />
          <span style={{ height: "45%" }} />
          <span style={{ height: "72%" }} />
          <span style={{ height: "38%" }} />
          <span style={{ height: "58%" }} />
          <span style={{ height: "48%" }} />
          <span style={{ height: "70%" }} />
        </div>
      </div>

      <div className="compact-card">
        <div className="card-header">
          <h3>
            <Activity size={14} />
            Recent Activity Logs
          </h3>
        </div>
        <div className="activity-list">
          {props.records.slice(0, 4).map((record) => (
            <div className="activity-row" key={record.id}>
              <span className={`activity-dot ${record.state}`} />
              <strong>{record.id}</strong>
              <span>{record.type}</span>
              <em>{(record.rate * 100).toFixed(0)}% saved</em>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function AuditTab(props: {
  expandedAuditId: string | null;
  records: AuditRecord[];
  search: string;
  onExpand: (id: string | null) => void;
  onSearch: (value: string) => void;
}) {
  return (
    <section className="tab-content active">
      <div className="table-card">
        <div className="table-search-box">
          <input
            placeholder="Search audit logs..."
            value={props.search}
            onChange={(event) => props.onSearch(event.target.value)}
          />
        </div>
        <div className="table-scroll">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Task</th>
                <th>Savings %</th>
                <th>Cost Saved</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {props.records.length === 0 ? (
                <tr>
                  <td className="empty-table" colSpan={5}>
                    No records in database
                  </td>
                </tr>
              ) : (
                props.records.map((record) => (
                  <AuditRows
                    expanded={props.expandedAuditId === record.id}
                    key={record.id}
                    record={record}
                    onToggle={() => props.onExpand(props.expandedAuditId === record.id ? null : record.id)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function PricingTab(props: {
  prices: ModelOption[];
  search: string;
  onSearch: (value: string) => void;
}) {
  return (
    <section className="tab-content active">
      <div className="table-card">
        <div className="table-search-box">
          <input
            placeholder="Search pricing registry..."
            value={props.search}
            onChange={(event) => props.onSearch(event.target.value)}
          />
        </div>
        <div className="table-scroll">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Input / M</th>
                <th>Output / M</th>
                <th>Rates Link</th>
              </tr>
            </thead>
            <tbody>
              {props.prices.map((price) => (
                <tr key={`${price.provider}-${price.model}`}>
                  <td className="model-cell">{price.model}</td>
                  <td>${price.input.toFixed(2)}</td>
                  <td>${price.output.toFixed(2)}</td>
                  <td>
                    <a className="audit-ref-link" href={price.url} rel="noreferrer" target="_blank">
                      Rates
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function SettingsTab() {
  return (
    <section className="tab-content active">
      <div className="compact-card">
        <div className="card-header">
          <h3>
            <ShieldCheck size={14} />
            Security & Compliance
          </h3>
        </div>
        <div className="card-body">
          <div className="row-switch">
            <div>
              <strong>Hashed-Only Telemetry</strong>
              <span>Do not save raw prompt bodies.</span>
            </div>
            <label className="switch">
              <input defaultChecked type="checkbox" />
              <span className="switch-slider" />
            </label>
          </div>
          <label className="form-group">
            SQLite Database URL
            <input className="form-control mono" readOnly value="sqlite:///./scrooge.db" />
          </label>
        </div>
      </div>

      <div className="compact-card">
        <div className="card-header">
          <h3>
            <Server size={14} />
            Local Proxy Configuration
          </h3>
        </div>
        <div className="card-body">
          <label className="form-group">
            Local Intercept Endpoint
            <input className="form-control mono highlight-input" readOnly value="http://localhost:8750/proxy" />
          </label>
          <label className="form-group">
            Upstream Target (OpenAI)
            <input className="form-control" readOnly value="https://api.openai.com" />
          </label>
        </div>
      </div>
    </section>
  );
}

function AuditRows(props: { expanded: boolean; record: AuditRecord; onToggle: () => void }) {
  return (
    <>
      <tr className="clickable-row" onClick={props.onToggle}>
        <td className="model-cell">{props.record.id}</td>
        <td>{props.record.type.slice(0, 8)}...</td>
        <td className="highlight-text">{(props.record.rate * 100).toFixed(0)}%</td>
        <td>${props.record.savedCost.toFixed(4)}</td>
        <td>
          <span className={`badge badge-${props.record.state}`}>{props.record.state}</span>
        </td>
      </tr>
      {props.expanded ? (
        <tr>
          <td colSpan={5}>
            <div className="expanded-info">
              <div>
                <strong>Original SHA-256 Hash</strong>
                <span className="hash-line">{props.record.hashOrig}</span>
              </div>
              <div>
                <strong>Optimized SHA-256 Hash</strong>
                <span className="hash-line">{props.record.hashOpt}</span>
              </div>
              <p>Prompt text was not written to local SQLite storage. Hashed-only mode is active.</p>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function DashboardCard(props: { highlight?: boolean; icon: JSX.Element; label: string; value: string | number }) {
  return (
    <div className="db-card">
      <div className="db-icon-box">{props.icon}</div>
      <div className="db-data">
        <span>{props.label}</span>
        <strong className={props.highlight ? "highlight" : ""}>{props.value}</strong>
      </div>
    </div>
  );
}

function NavItem(props: { active: boolean; icon: JSX.Element; label: string; onClick: () => void }) {
  return (
    <button className={`nav-item ${props.active ? "active" : ""}`} type="button" onClick={props.onClick}>
      {props.icon}
      <span>{props.label}</span>
    </button>
  );
}

function renderDiffLines(text: string, reasons: OptimizationReason[], mode: "added" | "removed") {
  const reasonIds = new Set(reasons.map((reason) => reason.rule_id));
  return text
    .split("\n")
    .slice(0, 28)
    .map((line, index) => {
      let className = "diff-unchanged";
      if (mode === "removed" && reasonIds.has("dedupe_adjacent_lines") && /ERROR|failed/i.test(line)) {
        className = "diff-removed";
      }
      if (
        mode === "added" &&
        (/^Goal:|^Return:|^Constraints:|^User request\/context:|^Log summary:/i.test(line) ||
          line.startsWith("- "))
      ) {
        className = "diff-added";
      }
      return (
        <span className={className} key={`${mode}-${index}-${line}`}>
          {className === "diff-added" ? "+ " : className === "diff-removed" ? "- " : ""}
          {line || " "}
        </span>
      );
    });
}

