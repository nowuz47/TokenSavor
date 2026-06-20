import {
  Activity,
  Award,
  Banknote,
  BarChart3,
  Check,
  CheckCircle,
  Clipboard,
  ClipboardCheck,
  Cpu,
  Database,
  Edit3,
  Eye,
  Flame,
  Languages,
  Minus,
  Moon,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Terminal,
  Trash2,
  X
} from "lucide-react";
import { readText, writeText } from "@tauri-apps/plugin-clipboard-manager";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useEffect, useMemo, useState } from "react";

import {
  approvePrompt,
  clearAuditRecords,
  getAuditRecords,
  getDashboardSummary,
  getRuntimeStatus,
  getQualitySummary,
  optimizePrompt
} from "./api";
import type {
  AuditRecordSummary,
  DashboardSummary,
  OptimizationReason,
  OptimizeResponse,
  QualitySummary,
  RuntimeStatus,
  TaskType
} from "./types";
import { copy, type Copy, type Locale } from "./i18n/copy";

type TabId = "workspace" | "dashboard" | "audit" | "pricing" | "settings";
type ThemeMode = "dark" | "light";

const APP_LOGO_SRC = "/scrooge_flat_no_coin.png";

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
  state: "sent" | "rejected" | "estimated" | "measured" | "failed";
  rules: string[];
  hashOrig: string;
  hashOpt: string;
  tokenizer: string;
  measuredInputTokens?: number | null;
  measuredOutputTokens?: number | null;
  measuredOriginalTokens?: number | null;
  rejectionReason?: string | null;
  providerUsageSource?: string | null;
  upstreamStatus?: number | null;
  captureSource: "manual" | "clipboard" | "hotkey" | "proxy";
  failureReason?: string | null;
  tokenizerConfidence: "estimated_local" | "estimated_provider_count" | "heuristic_fallback" | "provider_measured";
  tokenErrorRate?: number | null;
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
  { label: "Logs", value: "log_analysis" },
  { label: "Data", value: "data_analysis" }
];



const defaultPrompt = "";

function toAuditRecord(record: AuditRecordSummary): AuditRecord {
  return {
    id: record.request_id.slice(0, 10),
    time: new Date(record.created_at).toTimeString().split(" ")[0],
    provider: record.provider,
    model: record.model,
    type: record.task_type,
    originalTokens: record.original_tokens,
    optimizedTokens: record.optimized_tokens,
    savedTokens: record.saved_tokens,
    rate: record.savings_rate,
    savedCost: record.saved_cost_usd,
    state: record.state,
    rules: record.applied_rules,
    hashOrig: `sha256:${record.original_hash.slice(0, 8)}...`,
    hashOpt: `sha256:${record.optimized_hash.slice(0, 8)}...`,
    tokenizer: record.tokenizer_version,
    measuredInputTokens: record.measured_input_tokens,
    measuredOutputTokens: record.measured_output_tokens,
    measuredOriginalTokens: record.measured_original_tokens,
    rejectionReason: record.rejection_reason,
    providerUsageSource: record.provider_usage_source,
    upstreamStatus: record.upstream_status,
    captureSource: record.capture_source,
    failureReason: record.failure_reason,
    tokenizerConfidence: record.tokenizer_confidence,
    tokenErrorRate: record.token_error_rate
  };
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("workspace");
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-5.4-mini");
  const [taskType, setTaskType] = useState<TaskType | "">("");
  const [expectedOutputTokens, setExpectedOutputTokens] = useState(1000);
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [qualitySummary, setQualitySummary] = useState<QualitySummary | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);
  const [expandedAuditId, setExpandedAuditId] = useState<string | null>(null);
  const [auditSearch, setAuditSearch] = useState("");
  const [pricingSearch, setPricingSearch] = useState("");
  const [status, setStatus] = useState("Proxy Running (Port 8750)");
  const [toast, setToast] = useState("");
  const [proxyRunning, setProxyRunning] = useState(true);
  const [loading, setLoading] = useState(false);
  const [lastTelemetryRefresh, setLastTelemetryRefresh] = useState("Not synced yet");
  const [theme, setTheme] = useState<ThemeMode>(() =>
    window.localStorage.getItem("scrooge-theme") === "light" ? "light" : "dark"
  );
  const [locale, setLocale] = useState<Locale>(() =>
    window.localStorage.getItem("scrooge-locale") === "en" ? "en" : "ko"
  );
  const labels = copy[locale];

  const availableModels = useMemo(
    () => modelsRegistry.filter((item) => item.provider === provider),
    [provider]
  );

  const aggregate = useMemo(() => {
    return {
      savedTokens: summary?.saved_tokens ?? 0,
      savedCost: summary?.saved_cost_usd ?? 0,
      savingsRate: summary?.savings_rate ?? 0,
      approved: summary?.approved_requests ?? 0,
      totalAudits: summary?.total_requests ?? auditRecords.length,
      measuredRequests: summary?.measured_requests ?? 0,
      measurementCoverage: summary?.measurement_coverage ?? 0,
      avgTokenErrorRate: summary?.avg_token_error_rate ?? 0,
      maxTokenErrorRate: summary?.max_token_error_rate ?? 0,
      followupRequests: summary?.followup_requests ?? 0,
      reaskRate: summary?.reask_rate ?? 0,
      longContextSavingsRate: summary?.long_context_savings_rate ?? 0,
      shortPromptOverOptimizationCount: summary?.short_prompt_over_optimization_count ?? 0,
      hotkeySuccessRate: summary?.hotkey_success_rate ?? 0,
      backendHealthStatus: runtimeStatus?.backend_status ?? summary?.backend_health_status ?? "unknown",
      databaseStatus: runtimeStatus?.database_status ?? "unknown",
      qualityPreservationRate:
        summary?.quality_preservation_rate ?? qualitySummary?.quality_preservation_rate ?? 0
    };
  }, [auditRecords.length, qualitySummary, runtimeStatus, summary]);

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
    refreshTelemetry();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("scrooge-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.lang = locale;
    window.localStorage.setItem("scrooge-locale", locale);
    setStatus((current) => {
      if (current === copy.en.status.proxyRunning || current === copy.ko.status.proxyRunning) {
        return labels.status.proxyRunning;
      }
      if (current === copy.en.status.proxyInactive || current === copy.ko.status.proxyInactive) {
        return labels.status.proxyInactive;
      }
      return current;
    });
    setLastTelemetryRefresh((current) =>
      current === copy.en.status.notSynced || current === copy.ko.status.notSynced
        ? labels.status.notSynced
        : current
    );
  }, [labels, locale]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refreshTelemetry();
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (activeTab === "dashboard" || activeTab === "audit") {
      void refreshTelemetry();
    }
  }, [activeTab]);

  useEffect(() => {
    const refreshOnFocus = () => {
      if (document.visibilityState === "visible") {
        void refreshTelemetry();
      }
    };
    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnFocus);
    return () => {
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnFocus);
    };
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

  useEffect(() => {
    let disposed = false;
    const unlistenPromise = listen<{
      request_id?: string;
      saved_tokens?: number;
      status?: "empty" | "failed" | "no_savings" | "optimized";
    }>("scrooge-hotkey-result", async (event) => {
      if (disposed) return;
      await refreshTelemetry();
      const status = event.payload.status;
      if (status === "optimized") {
        showToast(`${labels.toast.hotkeyCopied} (${(event.payload.saved_tokens ?? 0).toLocaleString()} tokens)`);
      } else if (status === "no_savings") {
        showToast(labels.toast.hotkeyNoSavings);
      } else if (status === "failed") {
        showToast(labels.toast.hotkeyFailed);
      }
    });

    return () => {
      disposed = true;
      void unlistenPromise.then((unlisten) => unlisten());
    };
  }, [labels]);

  async function refreshTelemetry() {
    try {
      const [nextSummary, nextRecords, nextQuality, nextRuntime] = await Promise.all([
        getDashboardSummary("month"),
        getAuditRecords(100),
        getQualitySummary(),
        getRuntimeStatus()
      ]);
      setSummary(nextSummary);
      setAuditRecords(nextRecords.map(toAuditRecord));
      setQualitySummary(nextQuality);
      setRuntimeStatus(nextRuntime);
      setLastTelemetryRefresh(new Date().toLocaleTimeString());
    } catch {
      setSummary(null);
      setAuditRecords([]);
      setQualitySummary(null);
      setRuntimeStatus(null);
    }
  }

  async function runOptimize() {
    if (!proxyRunning) {
      showToast(labels.toast.disabled);
      return;
    }
    if (!prompt.trim()) {
      showToast(labels.toast.promptRequired);
      return;
    }
    setLoading(true);
    setStatus(locale === "ko" ? "요청 최적화 중" : "Optimizing request");
    try {
      const response = await optimizePrompt({
        prompt,
        provider,
        model,
        task_type: taskType,
        expected_output_tokens: expectedOutputTokens,
        capture_source: "manual"
      });
      setResult(response);
      setPrompt(response.optimized_prompt);
      setStatus(locale === "ko" ? "프롬프트 최적화됨" : "Prompt optimized");
      showToast(labels.toast.optimizedLoaded);
      await refreshTelemetry();
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
      await approvePrompt(result.request_id, approved, approved ? undefined : "user_kept_original");
      if (approved) {
        await copyOptimizedPrompt(result.optimized_prompt);
      }
      setStatus(approved ? (locale === "ko" ? "Codex용 최적화 프롬프트 복사됨" : "Optimized prompt copied for Codex") : (locale === "ko" ? "최적화 프롬프트 거절됨" : "Optimized prompt rejected"));
      showToast(approved ? labels.toast.optimizedCopied : labels.toast.optimizedRejected);
      setResult(null);
      await refreshTelemetry();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Approval failed";
      setStatus(message);
      showToast(message);
    } finally {
      setLoading(false);
    }
  }

  async function copyOptimizedPrompt(text: string) {
    await writeText(text);
  }

  async function captureClipboardPrompt() {
    try {
      const text = await readText();
      if (!text.trim()) {
        showToast(labels.toast.clipboardEmpty);
        return null;
      }
      setPrompt(text);
      setStatus(locale === "ko" ? "Codex 브리지가 클립보드 프롬프트를 캡처함" : "Codex Bridge captured clipboard prompt");
      showToast(labels.toast.clipboardCaptured);
      return text;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Clipboard capture failed";
      setStatus(message);
      showToast(message);
      return null;
    }
  }

  async function optimizeClipboardDirect() {
    if (!proxyRunning) {
      showToast(labels.toast.disabled);
      return;
    }
    try {
      const text = await readText();
      if (!text.trim()) {
        showToast(labels.toast.clipboardEmpty);
        return;
      }
      setLoading(true);
      setStatus(locale === "ko" ? "클립보드 즉시 최적화 중" : "Optimizing clipboard");
      const response = await optimizePrompt({
        prompt: text,
        provider,
        model,
        task_type: taskType,
        expected_output_tokens: expectedOutputTokens,
        capture_source: "clipboard"
      });
      if (response.saved_tokens <= 0) {
        await approvePrompt(response.request_id, false, "no_savings");
        setResult(response);
        setPrompt(text);
        setStatus(locale === "ko" ? "절감 없음 - 클립보드 유지" : "No savings - clipboard unchanged");
        showToast(labels.toast.hotkeyNoSavings);
        await refreshTelemetry();
        return;
      }
      await approvePrompt(response.request_id, true);
      await writeText(response.optimized_prompt);
      setResult(response);
      setPrompt(response.optimized_prompt);
      setStatus(locale === "ko" ? "클립보드가 최적화 프롬프트로 교체됨" : "Clipboard replaced with optimized prompt");
      showToast(labels.toast.hotkeyCopied);
      await refreshTelemetry();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Clipboard optimize failed";
      setStatus(message);
      showToast(message);
    } finally {
      setLoading(false);
    }
  }

  async function optimizeClipboardPrompt() {
    const text = await captureClipboardPrompt();
    if (!text?.trim()) return;
    setLoading(true);
    setStatus(locale === "ko" ? "Codex 클립보드 프롬프트 최적화 중" : "Optimizing Codex clipboard prompt");
    try {
      const response = await optimizePrompt({
        prompt: text,
        provider,
        model,
        task_type: taskType,
        expected_output_tokens: expectedOutputTokens,
        capture_source: "clipboard"
      });
      setResult(response);
      setPrompt(response.optimized_prompt);
      setStatus(locale === "ko" ? "Codex 브리지 프롬프트 최적화됨" : "Codex Bridge prompt optimized");
      showToast(labels.toast.clipboardOptimized);
      await refreshTelemetry();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Clipboard optimize failed";
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
      setStatus(next ? labels.status.proxyRunning : labels.status.proxyInactive);
      showToast(next ? labels.toast.proxyStarted : labels.toast.proxyBypass);
      return next;
    });
  }

  async function syncLogs() {
    await refreshTelemetry();
    showToast(labels.toast.refreshed);
  }

  async function clearLocalRecords() {
    try {
      await clearAuditRecords();
      setAuditRecords([]);
      setSummary(null);
      setExpandedAuditId(null);
      showToast(labels.toast.dbCleared);
      await refreshTelemetry();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Clear audit records failed";
      setStatus(message);
      showToast(message);
    }
  }

  async function minimizeWindow() {
    try {
      await getCurrentWindow().minimize();
    } catch {
      showToast(labels.toast.minimizeFallback);
    }
  }

  async function hideWindowToTray() {
    try {
      await getCurrentWindow().hide();
      showToast(labels.toast.hideFallback);
    } catch {
      showToast(labels.toast.hideFallback);
    }
  }

  const tabContent = {
    workspace: (
      <WorkspaceTab
        availableModels={availableModels}
        copy={labels}
        expectedOutputTokens={expectedOutputTokens}
        loading={loading}
        model={model}
        prompt={prompt}
        provider={provider}
        result={result}
        taskType={taskType}
        onExpectedOutputTokensChange={setExpectedOutputTokens}
        onModelChange={setModel}
        onOptimize={runOptimize}
        onPromptChange={setPrompt}
        onProviderChange={setProvider}
        onTaskTypeChange={setTaskType}
      />
    ),
    dashboard: (
      <DashboardTab
        aggregate={aggregate}
        copy={labels}
        lastTelemetryRefresh={lastTelemetryRefresh}
        qualitySummary={qualitySummary}
        records={auditRecords}
      />
    ),
    audit: (
      <AuditTab
        copy={labels}
        expandedAuditId={expandedAuditId}
        records={filteredAuditRecords}
        search={auditSearch}
        onExpand={setExpandedAuditId}
        onSearch={setAuditSearch}
      />
    ),
    pricing: (
      <PricingTab copy={labels} prices={filteredPrices} search={pricingSearch} onSearch={setPricingSearch} />
    ),
    settings: (
      <SettingsTab
        copy={labels}
        locale={locale}
        theme={theme}
        onLocaleChange={setLocale}
        onThemeChange={setTheme}
      />
    )
  } satisfies Record<TabId, JSX.Element>;

  return (
    <main className="app-container">
      <header className="app-header" data-tauri-drag-region>
        <div className="brand-group" data-tauri-drag-region>
          <div className="brand-logo">
            <img src={APP_LOGO_SRC} alt="Scrooge" />
          </div>
          <span className="brand-title">Scrooge</span>
        </div>
        <div className="header-metrics" data-tauri-drag-region>
          <span>{(aggregate.savingsRate * 100).toFixed(0)}%</span>
          <strong>${aggregate.savedCost.toFixed(2)}</strong>
        </div>
        <div className="window-actions">
          <button className="win-btn" type="button" title={labels.actions.minimize} onClick={minimizeWindow}>
            <Minus size={14} />
          </button>
          <button className="win-btn close" type="button" title={labels.actions.hideToTray} onClick={hideWindowToTray}>
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
          <span>scrooge.db ({aggregate.totalAudits} {labels.status.records}) - {labels.status.lastSync}: {lastTelemetryRefresh}</span>
          <button className="status-btn" type="button" onClick={syncLogs}>
            <RefreshCw size={11} />
            <span>{labels.actions.refresh}</span>
          </button>
          <button className="status-btn" type="button" onClick={clearLocalRecords}>
            <Trash2 size={11} />
            <span>{labels.actions.clearDb}</span>
          </button>
        </div>
      </div>

      <nav className="bottom-nav">
        <NavItem active={activeTab === "workspace"} icon={<SlidersHorizontal />} label={labels.nav.workspace} onClick={() => setActiveTab("workspace")} />
        <NavItem active={activeTab === "dashboard"} icon={<BarChart3 />} label={labels.nav.dashboard} onClick={() => setActiveTab("dashboard")} />
        <NavItem active={activeTab === "audit"} icon={<Database />} label={labels.nav.audit} onClick={() => setActiveTab("audit")} />
        <NavItem active={activeTab === "pricing"} icon={<Banknote />} label={labels.nav.pricing} onClick={() => setActiveTab("pricing")} />
        <NavItem active={activeTab === "settings"} icon={<Settings />} label={labels.nav.settings} onClick={() => setActiveTab("settings")} />
      </nav>

      <div className={`toast ${toast ? "active" : ""}`}>
        <CheckCircle size={16} />
        <span>{toast || labels.toast.defaultDone}</span>
      </div>
    </main>
  );
}

function WorkspaceTab(props: {
  availableModels: ModelOption[];
  copy: Copy;
  expectedOutputTokens: number;
  loading: boolean;
  model: string;
  prompt: string;
  provider: string;
  result: OptimizeResponse | null;
  taskType: TaskType | "";
  onExpectedOutputTokensChange: (value: number) => void;
  onModelChange: (value: string) => void;
  onOptimize: () => void;
  onPromptChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onTaskTypeChange: (value: TaskType | "") => void;
}) {
  return (
    <section className="tab-content active">
      <div className="easy-hero easy-hero-compact">
        <div className="easy-hero-main">
          <div className="easy-hero-logo">
            <img src={APP_LOGO_SRC} alt="" />
          </div>
          <div className="easy-hero-copy">
            <h2>{props.copy.workspace.heroTitle}</h2>
            <p>{props.copy.workspace.heroSubtitle}</p>
          </div>
        </div>
      </div>

      <div className="compact-card easy-input-card">
        <div className="card-header">
          <h3>
            <Terminal size={14} />
            {props.copy.workspace.pasteLabel}
          </h3>
        </div>
        <div className="card-body">
          <label className="form-group grow">
            {props.copy.workspace.context}
            <div className="editor-box">
              <textarea
                className="editor-textarea"
                placeholder={props.copy.workspace.placeholder}
                value={props.prompt}
                onChange={(event) => props.onPromptChange(event.target.value)}
              />
            </div>
          </label>
          <button className="btn btn-primary optimize-main-button" type="button" onClick={props.onOptimize} disabled={props.loading}>
            <Sparkles size={14} />
            {props.copy.actions.optimize}
          </button>
          {props.result ? <ImprovementInsights copy={props.copy} result={props.result} /> : null}
        </div>
      </div>

      <details className="advanced-panel">
        <summary>
          <SlidersHorizontal size={14} />
          <span>{props.copy.workspace.advanced}</span>
          <em>{props.copy.workspace.advancedNote}</em>
        </summary>
        <div className="advanced-body">
          <div className="bridge-grid">
            <div className="bridge-panel bridge-primary">
              <div className="bridge-title">
                <Server size={14} />
                <span>{props.copy.workspace.hookProxy}</span>
                <strong>{props.copy.workspace.primary}</strong>
              </div>
              <div className="hook-endpoint mono">http://127.0.0.1:8750/proxy/{props.provider}/v1/responses</div>
              <div className="bridge-chips">
                {props.copy.workspace.endpointChips.map((chip) => (
                  <span key={chip}>{chip}</span>
                ))}
              </div>
            </div>
            <div className="bridge-panel">
              <div className="bridge-title">
                <ClipboardCheck size={14} />
                <span>{props.copy.workspace.bridge}</span>
                <strong>{props.copy.workspace.assist}</strong>
              </div>
              <div className="hook-endpoint mono">{props.copy.workspace.hotkeyHint}</div>
            </div>
          </div>

          <div className="advanced-controls">
            <div className="form-row">
              <label className="form-group">
                {props.copy.workspace.provider}
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
                {props.copy.workspace.targetModel}
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
              {props.copy.workspace.maxOut}: {props.expectedOutputTokens}
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
              <span className="form-label">{props.copy.workspace.taskTemplate}</span>
              <div className="task-tags">
                {taskOptions.map((option) => (
                  <button
                    key={option.label}
                    className={`tag-btn ${props.taskType === option.value ? "active" : ""}`}
                    type="button"
                    onClick={() => props.onTaskTypeChange(option.value)}
                  >
                    {props.copy.taskOptions[(option.value || "auto") as keyof Copy["taskOptions"]]}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </details>
    </section>
  );
}

function ImprovementInsights(props: { copy: Copy; result: OptimizeResponse }) {
  const savedRate = `${(props.result.savings_rate * 100).toFixed(1)}%`;
  const savedTokens = `${props.result.saved_tokens.toLocaleString()} tokens`;
  const savedCost = `$${props.result.saved_cost_usd.toFixed(4)}`;
  const ruleSummary =
    props.result.reasons.length > 0
      ? props.result.reasons.slice(0, 2).map((reason) => reason.description).join(" / ")
      : props.copy.workspace.privacyNote;

  const items = [
    {
      icon: ShieldCheck,
      title: props.copy.workspace.analysisPreserve,
      body: props.copy.workspace.analysisPreserveText
    },
    {
      icon: Sparkles,
      title: props.copy.workspace.analysisCleanup,
      body: props.copy.workspace.analysisCleanupText
    },
    {
      icon: SlidersHorizontal,
      title: props.copy.workspace.analysisStructure,
      body: props.copy.workspace.analysisStructureText
    },
    {
      icon: Banknote,
      title: props.copy.workspace.analysisCost,
      body: `${savedTokens} · ${savedRate} · ${savedCost} · ${props.copy.workspace.analysisRules}: ${ruleSummary}`
    }
  ];

  return (
    <div className="improvement-panel">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div className="improvement-item" key={item.title}>
            <Icon size={14} />
            <div>
              <strong>{item.title}</strong>
              <p>{item.body}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PreviewPanel(props: {
  copy: Copy;
  result: OptimizeResponse | null;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <div className="compact-card preview-card">
      <div className="card-header">
        <h3>
          <Eye size={14} />
          {props.copy.preview.title}
        </h3>
        <div className="card-actions">
          <button className="btn btn-outline" type="button" disabled={!props.result} onClick={props.onReject}>
            <X size={12} />
            {props.copy.actions.reject}
          </button>
          <button className="btn btn-primary" type="button" disabled={!props.result} onClick={props.onApprove}>
            <Check size={12} />
            {props.copy.actions.approve}
          </button>
        </div>
      </div>

      {!props.result ? (
        <div className="empty-preview-pane">
          <Cpu size={28} />
          <p>{props.copy.preview.empty}</p>
        </div>
      ) : (
        <div className="card-body">
          <div className="token-bar">
            <div>
              {props.copy.preview.estimatedOriginal}: <strong>{props.result.original_tokens.input_tokens.toLocaleString()}</strong>
            </div>
            <div>
              {props.copy.preview.estimatedOptimized}: <strong>{props.result.optimized_tokens.input_tokens.toLocaleString()}</strong>
            </div>
            <span className="token-badge">{(props.result.savings_rate * 100).toFixed(1)}% {props.copy.preview.estimatedSaved}</span>
          </div>
          <div className="audit-footer-strip">
            <div>
              {props.copy.preview.tokenizer}: <strong>{props.result.optimized_tokens.tokenizer}</strong>
            </div>
            <span>{props.copy.preview.usageNote}</span>
          </div>

          <div className="form-group">
            <span className="form-label">{props.copy.preview.structuralChanges}</span>
            <div className="diff-tray-layout">
              <div className="diff-section">
                <div className="diff-header-line">{props.copy.preview.removed}</div>
                <div className="diff-body-text">
                  {renderDiffLines(props.result.original_prompt, props.result.reasons, "removed")}
                </div>
              </div>
              <div className="diff-section">
                <div className="diff-header-line">{props.copy.preview.added}</div>
                <div className="diff-body-text">
                  {renderDiffLines(props.result.optimized_prompt, props.result.reasons, "added")}
                </div>
              </div>
            </div>
          </div>

          <div className="form-group">
            <span className="form-label">{props.copy.preview.appliedRules}</span>
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
              {props.copy.preview.pricingRegistry}: <strong>{props.result.optimized_cost.pricing_version}</strong>
            </div>
            <a className="audit-ref-link" href={props.result.optimized_cost.source_url} rel="noreferrer" target="_blank">
              {props.copy.actions.verifyRates}
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

function DashboardTab(props: {
  aggregate: {
    approved: number;
    avgTokenErrorRate: number;
    backendHealthStatus: string;
    databaseStatus: string;
    followupRequests: number;
    hotkeySuccessRate: number;
    longContextSavingsRate: number;
    maxTokenErrorRate: number;
    measuredRequests: number;
    measurementCoverage: number;
    qualityPreservationRate: number;
    reaskRate: number;
    savedCost: number;
    savedTokens: number;
    savingsRate: number;
    shortPromptOverOptimizationCount: number;
    totalAudits: number;
  };
  copy: Copy;
  lastTelemetryRefresh: string;
  qualitySummary: QualitySummary | null;
  records: AuditRecord[];
}) {
  const quality = props.qualitySummary;
  const trendRecords = props.records
    .filter((record) => record.savedTokens > 0)
    .slice(0, 7)
    .reverse();
  const maxTrendSavedTokens = Math.max(0, ...trendRecords.map((record) => record.savedTokens));

  return (
    <section className="tab-content active">
      <div className="db-grid savings-summary-grid">
        <DashboardCard icon={<Flame />} label={props.copy.dashboard.estimatedSavings} value={`${(props.aggregate.savingsRate * 100).toFixed(1)}%`} highlight />
        <DashboardCard icon={<ShieldCheck />} label={props.copy.dashboard.qualityPreservation} value={`${(props.aggregate.qualityPreservationRate * 100).toFixed(0)}%`} />
        <DashboardCard icon={<RefreshCw />} label={props.copy.dashboard.reaskRate} value={`${(props.aggregate.reaskRate * 100).toFixed(1)}%`} />
        <DashboardCard icon={<Award />} label={props.copy.dashboard.savedTokens} value={formatTokenCount(props.aggregate.savedTokens)} />
      </div>

      <div className="chart-card">
        <div className="chart-title">{props.copy.dashboard.trend}</div>
        {trendRecords.length === 0 ? (
          <div className="chart-empty">
            <BarChart3 size={16} />
            <span>{props.copy.dashboard.noSavingsData}</span>
          </div>
        ) : (
          <div className="chart-holder" aria-label="Token savings trend">
            {trendRecords.map((record) => (
              <span
                key={record.id}
                title={`${record.id}: ${record.savedTokens.toLocaleString()} tokens`}
                style={{ height: `${Math.max(8, (record.savedTokens / maxTrendSavedTokens) * 100)}%` }}
              />
            ))}
          </div>
        )}
      </div>

      <div className="compact-card">
        <div className="card-header">
          <h3>
            <Activity size={14} />
            {props.copy.dashboard.recentActivity}
          </h3>
        </div>
        <div className="activity-list">
          {props.records.length === 0 ? (
            <div className="activity-empty">{props.copy.dashboard.noActivity}</div>
          ) : (
            props.records.slice(0, 4).map((record) => (
              <div className="activity-row" key={record.id}>
                <span className={`activity-dot ${record.state}`} />
                <strong>{record.id}</strong>
                <span>{record.type}</span>
                <em>{(record.rate * 100).toFixed(0)}% {props.copy.dashboard.saved}</em>
              </div>
            ))
          )}
        </div>
      </div>

      <details className="advanced-panel dashboard-details">
        <summary>
          <ShieldCheck size={14} />
          <span>{props.copy.dashboard.detailTitle}</span>
          <em>{props.copy.dashboard.telemetryNote} {props.copy.status.lastSync}: {props.lastTelemetryRefresh}</em>
        </summary>
        <div className="advanced-body">
          <div className="db-grid dashboard-detail-grid">
            <DashboardCard icon={<Database />} label={props.copy.dashboard.totalAudits} value={props.aggregate.totalAudits} />
            <DashboardCard icon={<RefreshCw />} label={props.copy.dashboard.followupRequests} value={props.aggregate.followupRequests} />
            <DashboardCard icon={<Banknote />} label={props.copy.dashboard.savedUsd} value={`$${props.aggregate.savedCost.toFixed(2)}`} />
            <DashboardCard icon={<Terminal />} label={props.copy.dashboard.longContextSavings} value={`${(props.aggregate.longContextSavingsRate * 100).toFixed(1)}%`} />
            <DashboardCard icon={<ClipboardCheck />} label={props.copy.dashboard.hotkeySuccess} value={`${(props.aggregate.hotkeySuccessRate * 100).toFixed(0)}%`} />
            <DashboardCard icon={<X />} label={props.copy.dashboard.shortOverOptimization} value={props.aggregate.shortPromptOverOptimizationCount} />
            <DashboardCard icon={<Server />} label={props.copy.dashboard.backendHealth} value={props.aggregate.backendHealthStatus} />
            <DashboardCard icon={<Database />} label={props.copy.dashboard.databaseHealth} value={props.aggregate.databaseStatus} />
            <DashboardCard icon={<ShieldCheck />} label={props.copy.dashboard.measuredCoverage} value={`${(props.aggregate.measurementCoverage * 100).toFixed(0)}%`} />
            <DashboardCard icon={<Activity />} label={props.copy.dashboard.avgTokenError} value={`${(props.aggregate.avgTokenErrorRate * 100).toFixed(1)}%`} />
            <DashboardCard
              highlight
              icon={<ShieldCheck />}
              label={props.copy.dashboard.qualityPreservation}
              value={quality ? `${(quality.quality_preservation_rate * 100).toFixed(0)}%` : "--"}
            />
            <DashboardCard
              icon={<CheckCircle />}
              label={props.copy.dashboard.goldenCases}
              value={quality ? `${quality.passed_cases}/${quality.total_cases}` : "--"}
            />
            <DashboardCard
              icon={<X />}
              label={props.copy.dashboard.harmfulOmissions}
              value={quality?.harmful_omission_count ?? "--"}
            />
          </div>

          <div className="table-card">
            <div className="quality-card-header">
              <h3>
                <ShieldCheck size={14} />
                {props.copy.dashboard.qualityTitle}
              </h3>
              <span>
                {quality
                  ? `${(quality.average_savings_rate * 100).toFixed(1)}% ${props.copy.dashboard.avgSaved}`
                  : props.copy.dashboard.noQuality}
              </span>
            </div>
            <div className="table-scroll">
              <table className="compact-table quality-table">
                <thead>
                  <tr>
                    <th>{props.copy.dashboard.workType}</th>
                    <th>{props.copy.dashboard.cases}</th>
                    <th>{props.copy.dashboard.preserve}</th>
                    <th>{props.copy.dashboard.avgSaved}</th>
                    <th>{props.copy.dashboard.issues}</th>
                  </tr>
                </thead>
                <tbody>
                  {quality ? (
                    quality.category_summaries.map((item) => (
                      <tr key={item.category}>
                        <td className="model-cell">{formatQualityCategory(item.category, props.copy)}</td>
                        <td>{item.passed_cases}/{item.total_cases}</td>
                        <td>{(item.preservation_pass_rate * 100).toFixed(0)}%</td>
                        <td className="highlight-text">{(item.average_savings_rate * 100).toFixed(1)}%</td>
                        <td>
                          {item.harmful_omission_count +
                            item.hallucinated_constraint_count +
                            item.over_optimization_count +
                            item.savings_floor_failures}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="empty-table" colSpan={5}>
                        {props.copy.dashboard.noQuality}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </details>
    </section>
  );
}

function AuditTab(props: {
  copy: Copy;
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
            placeholder={props.copy.audit.search}
            value={props.search}
            onChange={(event) => props.onSearch(event.target.value)}
          />
        </div>
        <div className="table-scroll">
          <table className="compact-table">
            <thead>
              <tr>
                <th>{props.copy.audit.requestId}</th>
                <th>{props.copy.audit.task}</th>
                <th>{props.copy.dashboard.estimatedSavings}</th>
                <th>{props.copy.audit.costSaved}</th>
                <th>{props.copy.audit.state}</th>
              </tr>
            </thead>
            <tbody>
              {props.records.length === 0 ? (
                <tr>
                  <td className="empty-table" colSpan={5}>
                    {props.copy.audit.empty}
                  </td>
                </tr>
              ) : (
                props.records.map((record) => (
                  <AuditRows
                    copy={props.copy}
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
  copy: Copy;
  prices: ModelOption[];
  search: string;
  onSearch: (value: string) => void;
}) {
  return (
    <section className="tab-content active">
      <div className="table-card">
        <div className="table-search-box">
          <input
            placeholder={props.copy.pricing.search}
            value={props.search}
            onChange={(event) => props.onSearch(event.target.value)}
          />
        </div>
        <div className="table-scroll">
          <table className="compact-table">
            <thead>
              <tr>
                <th>{props.copy.pricing.model}</th>
                <th>{props.copy.pricing.input}</th>
                <th>{props.copy.pricing.output}</th>
                <th>{props.copy.pricing.ratesLink}</th>
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
                      {props.copy.pricing.rates}
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

function SettingsTab(props: {
  copy: Copy;
  locale: Locale;
  theme: ThemeMode;
  onLocaleChange: (value: Locale) => void;
  onThemeChange: (value: ThemeMode) => void;
}) {
  return (
    <section className="tab-content active">
      <div className="compact-card settings-brand-card">
        <div className="settings-brand-logo">
          <img src={APP_LOGO_SRC} alt="Scrooge" />
        </div>
        <div className="settings-brand-copy">
          <span>{props.copy.settings.brand}</span>
          <strong>{props.copy.settings.subtitle}</strong>
        </div>
      </div>

      <div className="compact-card">
        <div className="card-header">
          <h3>
            <Languages size={14} />
            {props.copy.nav.settings}
          </h3>
        </div>
        <div className="card-body">
          <label className="row-switch control-row">
            <div>
              <strong>{props.copy.settings.theme}</strong>
              <span>{props.copy.settings.themeNote}</span>
            </div>
            <select
              className="form-control compact-select"
              value={props.theme}
              onChange={(event) => props.onThemeChange(event.target.value as ThemeMode)}
            >
              <option value="dark">{props.copy.themeOptions.dark}</option>
              <option value="light">{props.copy.themeOptions.light}</option>
            </select>
            {props.theme === "dark" ? <Moon size={14} /> : <Sun size={14} />}
          </label>

          <label className="row-switch control-row">
            <div>
              <strong>{props.copy.settings.language}</strong>
              <span>{props.copy.settings.languageNote}</span>
            </div>
            <select
              className="form-control compact-select"
              value={props.locale}
              onChange={(event) => props.onLocaleChange(event.target.value as Locale)}
            >
              <option value="ko">{props.copy.languageOptions.ko}</option>
              <option value="en">{props.copy.languageOptions.en}</option>
            </select>
          </label>

          <div className="row-switch">
            <div>
              <strong>{props.copy.settings.hotkey}</strong>
              <span>{props.copy.settings.hotkeyNote}</span>
            </div>
            <span className="shortcut-key">Ctrl+Alt+S</span>
          </div>
        </div>
      </div>

      <div className="compact-card">
        <div className="card-header">
          <h3>
            <ShieldCheck size={14} />
            {props.copy.settings.compliance}
          </h3>
        </div>
        <div className="card-body">
          <div className="row-switch">
            <div>
              <strong>{props.copy.settings.hashedOnly}</strong>
              <span>{props.copy.settings.hashedOnlyNote}</span>
            </div>
            <label className="switch">
              <input defaultChecked type="checkbox" />
              <span className="switch-slider" />
            </label>
          </div>
          <label className="form-group">
            {props.copy.settings.databaseUrl}
            <input className="form-control mono" readOnly value="sqlite:///./scrooge.db" />
          </label>
        </div>
      </div>

      <div className="compact-card">
        <div className="card-header">
          <h3>
            <Server size={14} />
            {props.copy.settings.proxyConfig}
          </h3>
        </div>
        <div className="card-body">
          <label className="form-group">
            {props.copy.settings.localEndpoint}
            <input className="form-control mono highlight-input" readOnly value="http://127.0.0.1:8750/proxy/openai/v1/responses" />
          </label>
          <label className="form-group">
            {props.copy.settings.forwardHeader}
            <input className="form-control mono" readOnly value="x-scrooge-forward: true" />
          </label>
          <label className="form-group">
            {props.copy.settings.upstream}
            <input className="form-control" readOnly value="https://api.openai.com" />
          </label>
        </div>
      </div>
    </section>
  );
}

function AuditRows(props: { copy: Copy; expanded: boolean; record: AuditRecord; onToggle: () => void }) {
  return (
    <>
      <tr className="clickable-row" onClick={props.onToggle}>
        <td className="model-cell">{props.record.id}</td>
        <td>{props.record.type.slice(0, 8)}...</td>
        <td className="highlight-text">{(props.record.rate * 100).toFixed(0)}%</td>
        <td>${props.record.savedCost.toFixed(4)}</td>
        <td>
          <span className={`badge badge-${props.record.state}`}>
            {formatUsageState(props.record.state, props.copy)}
          </span>
          {props.record.state === "rejected" ? (
            <span className="state-reason">
              {formatRejectionReason(props.record.rejectionReason, props.copy)}
            </span>
          ) : null}
        </td>
      </tr>
      {props.expanded ? (
        <tr>
          <td colSpan={5}>
            <div className="expanded-info">
              <div>
                <strong>{props.copy.audit.originalHash}</strong>
                <span className="hash-line">{props.record.hashOrig}</span>
              </div>
              <div>
                <strong>{props.copy.audit.optimizedHash}</strong>
                <span className="hash-line">{props.record.hashOpt}</span>
              </div>
              <p>{props.copy.audit.privacy}</p>
              <div>
                <strong>{props.copy.audit.tokenSource}</strong>
                <span className="hash-line">{props.record.tokenizer}</span>
              </div>
              <div>
                <strong>{props.copy.audit.tokenizerConfidence}</strong>
                <span className="hash-line">{props.record.tokenizerConfidence}</span>
              </div>
              <div>
                <strong>{props.copy.audit.captureSource}</strong>
                <span className="hash-line">{props.record.captureSource}</span>
              </div>
              {props.record.failureReason ? (
                <div>
                  <strong>{props.copy.audit.failureReason}</strong>
                  <span className="hash-line">{props.record.failureReason}</span>
                </div>
              ) : null}
              {props.record.state === "measured" ? (
                <div>
                  <strong>{props.copy.audit.measuredUsage}</strong>
                  <span className="hash-line">
                    input {props.record.measuredInputTokens?.toLocaleString()} / output{" "}
                    {props.record.measuredOutputTokens?.toLocaleString()} / error{" "}
                    {(((props.record.tokenErrorRate ?? 0) * 100)).toFixed(1)}%
                  </span>
                </div>
              ) : (
                <p>{props.copy.audit.usageEstimated}</p>
              )}
              {props.record.providerUsageSource ? (
                <div>
                  <strong>{props.copy.audit.providerUsageSource}</strong>
                  <span className="hash-line">{props.record.providerUsageSource}</span>
                </div>
              ) : null}
              {props.record.upstreamStatus ? (
                <div>
                  <strong>{props.copy.audit.upstreamStatus}</strong>
                  <span className="hash-line">{props.record.upstreamStatus}</span>
                </div>
              ) : null}
              {props.record.state === "rejected" ? (
                <div>
                  <strong>{props.copy.audit.rejectionReason}</strong>
                  <span className="hash-line">
                    {formatRejectionReason(props.record.rejectionReason, props.copy)}
                  </span>
                </div>
              ) : null}
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

function formatQualityCategory(category: string, labels: Copy) {
  return labels.qualityCategories[category as keyof Copy["qualityCategories"]] ?? category;
}

function formatUsageState(state: AuditRecord["state"], labels: Copy) {
  return labels.audit.stateLabels[state] ?? state;
}

function formatRejectionReason(reason: string | null | undefined, labels: Copy) {
  const key = reason as keyof Copy["audit"]["rejectionReasons"] | undefined;
  return key && labels.audit.rejectionReasons[key]
    ? labels.audit.rejectionReasons[key]
    : labels.audit.rejectionReasons.unknown;
}

function formatTokenCount(tokens: number) {
  if (tokens < 1000) return tokens.toLocaleString();
  if (tokens < 1_000_000) return `${(tokens / 1000).toFixed(tokens < 10_000 ? 1 : 0)}K`;
  return `${(tokens / 1_000_000).toFixed(1)}M`;
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

