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
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useEffect, useMemo, useState } from "react";

import {
  approvePrompt,
  clearAuditRecords,
  getAuditRecords,
  getDashboardSummary,
  getQualitySummary,
  optimizePrompt
} from "./api";
import type {
  AuditRecordSummary,
  DashboardSummary,
  OptimizationReason,
  OptimizeResponse,
  QualitySummary,
  TaskType
} from "./types";

type TabId = "workspace" | "dashboard" | "audit" | "pricing" | "settings";
type WorkspacePanel = "input" | "preview";
type ThemeMode = "dark" | "light";
type Locale = "ko" | "en";

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
  { label: "Logs", value: "log_analysis" }
];

const copy = {
  en: {
    nav: {
      workspace: "Workspace",
      dashboard: "Dashboard",
      audit: "Audit Logs",
      pricing: "Rates",
      settings: "Settings"
    },
    actions: {
      approve: "Approve",
      capture: "Capture",
      clearDb: "Clear DB",
      hideToTray: "Hide to tray",
      minimize: "Minimize",
      optimize: "Optimize",
      optimizeClip: "Optimize Clip",
      optimizeHotkey: "Optimize Clipboard",
      refresh: "Refresh",
      reject: "Reject",
      verifyRates: "Verify Official Rates"
    },
    status: {
      proxyRunning: "Proxy Running (Port 8750)",
      proxyInactive: "Proxy Inactive (Stopped)",
      records: "records",
      lastSync: "Last sync",
      notSynced: "Not synced yet"
    },
    toast: {
      clipboardCaptured: "Clipboard prompt captured for optimization.",
      clipboardEmpty: "Clipboard is empty.",
      clipboardOptimized: "Review and approve to copy the optimized prompt.",
      hotkeyCopied: "Clipboard optimized and replaced. Paste it into Codex.",
      hotkeyNoSavings: "No token savings found. Clipboard was left unchanged.",
      hotkeyRegistered: "Global shortcut ready: Ctrl+Alt+S",
      hotkeyRegisterFailed: "Global shortcut registration failed. Use the Optimize Clipboard button.",
      dbCleared: "Local SQLite audit records cleared.",
      defaultDone: "Task complete.",
      disabled: "Optimization disabled while proxy router is stopped.",
      hideFallback: "Scrooge tray daemon keeps running.",
      minimizeFallback: "Window minimize is available in the installed desktop app.",
      optimizedCopied: "Optimized prompt copied. Paste it into Codex.",
      optimizedLoaded: "Optimization preview loaded.",
      optimizedRejected: "Optimized prompt rejected.",
      promptRequired: "Paste context or a request first.",
      proxyBypass: "Requests will bypass optimization.",
      proxyStarted: "Scrooge local proxy router started.",
      refreshed: "Dashboard refreshed from local hook telemetry."
    },
    workspace: {
      assist: "Assist",
      bridge: "Codex Bridge",
      context: "Context / Query Body",
      endpointChips: ["capture", "rewrite", "forward"],
      hotkeyHint: "Copy text in Codex, press Ctrl+Alt+S, then paste the optimized prompt.",
      hookProxy: "Hook Proxy",
      inputTab: "Workbench Input",
      maxOut: "Max Out Tokens",
      originalRequest: "Original Request",
      placeholder: "Paste noisy logs or code blocks here...",
      previewTab: "Optimization View",
      primary: "Primary",
      provider: "Provider",
      targetModel: "Target Model",
      taskTemplate: "Task Template"
    },
    preview: {
      added: "ADDED / TARGET DIRECTIVES",
      appliedRules: "Applied Reduction Rules",
      empty: "Run prompt optimization first under the workbench tab to view savings and code diffs.",
      estimatedOptimized: "Estimated optimized",
      estimatedOriginal: "Estimated original",
      estimatedSaved: "Estimated Saved",
      pricingRegistry: "Pricing Registry",
      removed: "REMOVED / CLEANED UP",
      structuralChanges: "Structural Context Changes",
      title: "Optimization Preview",
      tokenizer: "Tokenizer",
      usageNote: "Measured usage will replace estimates after provider usage is recorded."
    },
    dashboard: {
      avgSaved: "avg savings",
      avgTokenError: "Avg Token Error",
      cases: "Cases",
      estimatedSavings: "Estimated/Measured Savings",
      goldenCases: "Golden Cases",
      harmfulOmissions: "Harmful Omissions",
      issues: "Issues",
      measuredCoverage: "Measured Coverage",
      noQuality: "Quality gate summary unavailable",
      overOptimization: "Over-Optimization",
      preserve: "Preserve",
      qualityPreservation: "Quality Preservation",
      qualityTitle: "Quality Uniformity By Work Type",
      recentActivity: "Recent Activity Logs",
      saved: "saved",
      savedTokens: "Saved Tokens",
      savedUsd: "Saved USD",
      telemetryNote: "Local hook telemetry refreshes every 5 seconds.",
      totalAudits: "Total Audits",
      trend: "Token Savings Trend",
      workType: "Work Type"
    },
    audit: {
      costSaved: "Cost Saved",
      empty: "No records in database",
      measuredUsage: "Measured usage",
      optimizedHash: "Optimized SHA-256 Hash",
      originalHash: "Original SHA-256 Hash",
      privacy: "Prompt text was not written to local SQLite storage. Hashed-only mode is active.",
      requestId: "Request ID",
      search: "Search audit logs...",
      state: "State",
      task: "Task",
      tokenSource: "Token source",
      usageEstimated: "Usage is estimated until provider usage metadata is recorded."
    },
    pricing: {
      input: "Input / M",
      model: "Model",
      output: "Output / M",
      rates: "Rates",
      ratesLink: "Rates Link",
      search: "Search pricing registry..."
    },
    settings: {
      brand: "Scrooge Desktop",
      compliance: "Security & Compliance",
      databaseUrl: "SQLite Database URL",
      forwardHeader: "Forward Header",
      hashedOnly: "Hashed-Only Telemetry",
      hashedOnlyNote: "Do not save raw prompt bodies.",
      hotkey: "Global Shortcut",
      hotkeyNote: "Ctrl+Alt+S optimizes current clipboard text and replaces it with the optimized prompt.",
      language: "Language",
      languageNote: "Switch primary UI labels between Korean and English.",
      localEndpoint: "Local Hook Endpoint",
      proxyConfig: "Local Proxy Configuration",
      subtitle: "Local-first token efficiency guardrail",
      theme: "Theme",
      themeNote: "Use dark or light mode for the desktop shell.",
      upstream: "Upstream Target (OpenAI)"
    },
    languageOptions: {
      en: "English",
      ko: "Korean"
    },
    themeOptions: {
      dark: "Dark",
      light: "Light"
    },
    taskOptions: {
      auto: "Auto",
      bug_analysis: "Bug",
      code_review: "Review",
      refactoring: "Refactor",
      test_generation: "Test",
      log_analysis: "Logs"
    },
    qualityCategories: {
      coding: "Coding",
      debugging: "Debugging",
      logs: "Logs",
      data: "Data",
      docs_planning: "Docs/Planning"
    }
  },
  ko: {
    nav: {
      workspace: "작업",
      dashboard: "대시보드",
      audit: "감사 로그",
      pricing: "단가",
      settings: "설정"
    },
    actions: {
      approve: "승인",
      capture: "캡처",
      clearDb: "DB 삭제",
      hideToTray: "트레이로 숨기기",
      minimize: "최소화",
      optimize: "최적화",
      optimizeClip: "클립보드 최적화",
      optimizeHotkey: "클립보드 즉시 최적화",
      refresh: "새로고침",
      reject: "거절",
      verifyRates: "공식 단가 확인"
    },
    status: {
      proxyRunning: "프록시 실행 중 (8750)",
      proxyInactive: "프록시 중지됨",
      records: "건",
      lastSync: "마지막 동기화",
      notSynced: "아직 동기화 안 됨"
    },
    toast: {
      clipboardCaptured: "클립보드 프롬프트를 최적화 대상으로 가져왔습니다.",
      clipboardEmpty: "클립보드가 비어 있습니다.",
      clipboardOptimized: "검토 후 승인하면 최적화 프롬프트를 복사합니다.",
      hotkeyCopied: "클립보드를 최적화 프롬프트로 교체했습니다. Codex에 붙여넣으세요.",
      hotkeyNoSavings: "절감 가능한 토큰이 없어 클립보드를 원문 그대로 유지했습니다.",
      hotkeyRegistered: "전역 단축키 준비됨: Ctrl+Alt+S",
      hotkeyRegisterFailed: "전역 단축키 등록 실패. 클립보드 최적화 버튼을 사용하세요.",
      dbCleared: "로컬 SQLite 감사 기록을 삭제했습니다.",
      defaultDone: "작업이 완료되었습니다.",
      disabled: "프록시 라우터가 중지되어 최적화를 사용할 수 없습니다.",
      hideFallback: "Scrooge 트레이 데몬은 계속 실행됩니다.",
      minimizeFallback: "설치된 데스크톱 앱에서 창 최소화를 사용할 수 있습니다.",
      optimizedCopied: "최적화 프롬프트를 복사했습니다. Codex에 붙여넣으세요.",
      optimizedLoaded: "최적화 미리보기를 불러왔습니다.",
      optimizedRejected: "최적화 프롬프트를 거절했습니다.",
      promptRequired: "먼저 요청이나 컨텍스트를 입력하세요.",
      proxyBypass: "요청이 최적화를 우회합니다.",
      proxyStarted: "Scrooge 로컬 프록시 라우터를 시작했습니다.",
      refreshed: "로컬 후킹 텔레메트리에서 대시보드를 새로고침했습니다."
    },
    workspace: {
      assist: "보조",
      bridge: "Codex 브리지",
      context: "컨텍스트 / 요청 본문",
      endpointChips: ["수집", "재작성", "전송"],
      hotkeyHint: "Codex에서 텍스트를 복사하고 Ctrl+Alt+S를 누른 뒤 최적화 프롬프트를 붙여넣으세요.",
      hookProxy: "후킹 프록시",
      inputTab: "입력 작업대",
      maxOut: "최대 출력 토큰",
      originalRequest: "원본 요청",
      placeholder: "긴 로그나 코드 블록을 붙여넣으세요...",
      previewTab: "최적화 보기",
      primary: "기본",
      provider: "Provider",
      targetModel: "대상 모델",
      taskTemplate: "작업 템플릿"
    },
    preview: {
      added: "추가 / 목표 지시",
      appliedRules: "적용된 절감 규칙",
      empty: "먼저 작업 탭에서 프롬프트 최적화를 실행하면 절감량과 변경 내용을 볼 수 있습니다.",
      estimatedOptimized: "추정 최적화",
      estimatedOriginal: "추정 원본",
      estimatedSaved: "예상 절감",
      pricingRegistry: "가격표 버전",
      removed: "제거 / 정리",
      structuralChanges: "구조적 컨텍스트 변경",
      title: "최적화 미리보기",
      tokenizer: "토크나이저",
      usageNote: "provider 사용량이 기록되면 추정값이 실측값으로 대체됩니다."
    },
    dashboard: {
      avgSaved: "평균 절감",
      avgTokenError: "평균 토큰 오차",
      cases: "케이스",
      estimatedSavings: "예상/실측 절감률",
      goldenCases: "골든 케이스",
      harmfulOmissions: "심각 누락",
      issues: "이슈",
      measuredCoverage: "실측 커버리지",
      noQuality: "품질 게이트 요약을 불러올 수 없습니다",
      overOptimization: "과최적화",
      preserve: "보존율",
      qualityPreservation: "품질 보존율",
      qualityTitle: "작업 유형별 품질 균일성",
      recentActivity: "최근 활동 로그",
      saved: "절감",
      savedTokens: "절감 토큰",
      savedUsd: "절감 비용",
      telemetryNote: "로컬 후킹 텔레메트리는 5초마다 새로고침됩니다.",
      totalAudits: "전체 감사",
      trend: "토큰 절감 추이",
      workType: "작업 유형"
    },
    audit: {
      costSaved: "절감 비용",
      empty: "데이터베이스에 기록이 없습니다",
      measuredUsage: "실측 사용량",
      optimizedHash: "최적화 SHA-256 해시",
      originalHash: "원본 SHA-256 해시",
      privacy: "프롬프트 전문은 로컬 SQLite에 저장하지 않습니다. 해시 전용 모드가 활성화되어 있습니다.",
      requestId: "요청 ID",
      search: "감사 로그 검색...",
      state: "상태",
      task: "작업",
      tokenSource: "토큰 기준",
      usageEstimated: "provider 사용량 메타데이터가 기록될 때까지 추정값으로 표시됩니다."
    },
    pricing: {
      input: "입력 / M",
      model: "모델",
      output: "출력 / M",
      rates: "단가",
      ratesLink: "단가 링크",
      search: "가격표 검색..."
    },
    settings: {
      brand: "Scrooge 데스크톱",
      compliance: "보안 및 컴플라이언스",
      databaseUrl: "SQLite 데이터베이스 URL",
      forwardHeader: "전송 헤더",
      hashedOnly: "해시 전용 텔레메트리",
      hashedOnlyNote: "원본 프롬프트 본문을 저장하지 않습니다.",
      hotkey: "전역 단축키",
      hotkeyNote: "Ctrl+Alt+S가 현재 클립보드 텍스트를 최적화하고 클립보드를 교체합니다.",
      language: "언어",
      languageNote: "주요 UI 문구를 한국어/영어로 전환합니다.",
      localEndpoint: "로컬 후킹 엔드포인트",
      proxyConfig: "로컬 프록시 설정",
      subtitle: "로컬 우선 토큰 효율 가드레일",
      theme: "테마",
      themeNote: "데스크톱 셸을 다크/라이트 모드로 전환합니다.",
      upstream: "업스트림 대상 (OpenAI)"
    },
    languageOptions: {
      en: "영어",
      ko: "한국어"
    },
    themeOptions: {
      dark: "다크",
      light: "라이트"
    },
    taskOptions: {
      auto: "자동",
      bug_analysis: "버그",
      code_review: "리뷰",
      refactoring: "리팩터링",
      test_generation: "테스트",
      log_analysis: "로그"
    },
    qualityCategories: {
      coding: "코딩",
      debugging: "디버깅",
      logs: "로그",
      data: "데이터",
      docs_planning: "문서/기획"
    }
  }
} as const;

type Copy = (typeof copy)[Locale];

const defaultPrompt =
  "이 코드가 이상한 것 같은데 한번 확인해 주세요.\n\n" +
  "ERROR 12:04:15 c.s.config.ServerBootstrap - failed to parse config\n" +
  "ERROR 12:04:15 c.s.config.ServerBootstrap - failed to parse config\n" +
  "ERROR 12:04:15 c.s.config.ServerBootstrap - failed to parse config\n" +
  "Traceback (most recent call last):\n" +
  '  File "/app/scrooge/config.py", line 45, in parse_yaml\n' +
  "    config = yaml.safe_load(f)\n" +
  "yaml.parser.ParserError: expected '<document start>', but found '<block start>'";

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
    tokenErrorRate: record.token_error_rate
  };
}

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
  const [qualitySummary, setQualitySummary] = useState<QualitySummary | null>(null);
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
      maxTokenErrorRate: summary?.max_token_error_rate ?? 0
    };
  }, [auditRecords.length, summary]);

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

  async function refreshTelemetry() {
    try {
      const [nextSummary, nextRecords, nextQuality] = await Promise.all([
        getDashboardSummary("month"),
        getAuditRecords(100),
        getQualitySummary()
      ]);
      setSummary(nextSummary);
      setAuditRecords(nextRecords.map(toAuditRecord));
      setQualitySummary(nextQuality);
      setLastTelemetryRefresh(new Date().toLocaleTimeString());
    } catch {
      setSummary(null);
      setAuditRecords([]);
      setQualitySummary(null);
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
        expected_output_tokens: expectedOutputTokens
      });
      setResult(response);
      setWorkspacePanel("preview");
      setStatus(locale === "ko" ? "최적화 미리보기 로드됨" : "Optimization preview loaded");
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
      await approvePrompt(result.request_id, approved);
      if (approved) {
        await copyOptimizedPrompt(result.optimized_prompt);
      }
      setStatus(approved ? (locale === "ko" ? "Codex용 최적화 프롬프트 복사됨" : "Optimized prompt copied for Codex") : (locale === "ko" ? "최적화 프롬프트 거절됨" : "Optimized prompt rejected"));
      showToast(approved ? labels.toast.optimizedCopied : labels.toast.optimizedRejected);
      setResult(null);
      setWorkspacePanel("input");
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
      setWorkspacePanel("input");
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
        expected_output_tokens: expectedOutputTokens
      });
      if (response.saved_tokens <= 0) {
        await approvePrompt(response.request_id, false);
        setResult(response);
        setPrompt(text);
        setWorkspacePanel("preview");
        setStatus(locale === "ko" ? "절감 없음 - 클립보드 유지" : "No savings - clipboard unchanged");
        showToast(labels.toast.hotkeyNoSavings);
        await refreshTelemetry();
        return;
      }
      await approvePrompt(response.request_id, true);
      await writeText(response.optimized_prompt);
      setResult(response);
      setPrompt(text);
      setWorkspacePanel("preview");
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
        expected_output_tokens: expectedOutputTokens
      });
      setResult(response);
      setWorkspacePanel("preview");
      setStatus(locale === "ko" ? "Codex 브리지 미리보기 로드됨" : "Codex Bridge preview loaded");
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
      await getCurrentWindow().close();
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
        workspacePanel={workspacePanel}
        onApprove={() => decide(true)}
        onCaptureClipboard={captureClipboardPrompt}
        onExpectedOutputTokensChange={setExpectedOutputTokens}
        onModelChange={setModel}
        onOptimize={runOptimize}
        onOptimizeClipboard={optimizeClipboardPrompt}
        onOptimizeClipboardDirect={optimizeClipboardDirect}
        onPromptChange={setPrompt}
        onProviderChange={setProvider}
        onReject={() => decide(false)}
        onTaskTypeChange={setTaskType}
        onWorkspacePanelChange={setWorkspacePanel}
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
  workspacePanel: WorkspacePanel;
  onApprove: () => void;
  onCaptureClipboard: () => void;
  onExpectedOutputTokensChange: (value: number) => void;
  onModelChange: (value: string) => void;
  onOptimize: () => void;
  onOptimizeClipboard: () => void;
  onOptimizeClipboardDirect: () => void;
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
          {props.copy.workspace.inputTab}
        </button>
        <button
          className={`panel-toggle-btn ${props.workspacePanel === "preview" ? "active" : ""}`}
          type="button"
          onClick={() => props.onWorkspacePanelChange("preview")}
        >
          <Eye size={12} />
          {props.copy.workspace.previewTab}
        </button>
      </div>

      {props.workspacePanel === "input" ? (
        <>
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
              <div className="bridge-actions">
                <button className="btn btn-primary" type="button" onClick={props.onOptimizeClipboardDirect} disabled={props.loading}>
                  <Sparkles size={12} />
                  {props.copy.actions.optimizeHotkey}
                </button>
                <button className="btn btn-outline" type="button" onClick={props.onCaptureClipboard} disabled={props.loading}>
                  <Clipboard size={12} />
                  {props.copy.actions.capture}
                </button>
                <button className="btn btn-outline" type="button" onClick={props.onOptimizeClipboard} disabled={props.loading}>
                  <Sparkles size={12} />
                  {props.copy.actions.optimizeClip}
                </button>
              </div>
              <div className="hook-endpoint mono">{props.copy.workspace.hotkeyHint}</div>
            </div>
          </div>

          <div className="compact-card">
            <div className="card-header">
              <h3>
                <Terminal size={14} />
                {props.copy.workspace.originalRequest}
              </h3>
              <button className="btn btn-primary" type="button" onClick={props.onOptimize} disabled={props.loading}>
                <Sparkles size={12} />
                {props.copy.actions.optimize}
              </button>
            </div>
            <div className="card-body">
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
            </div>
          </div>
        </>
      ) : (
        <PreviewPanel copy={props.copy} result={props.result} onApprove={props.onApprove} onReject={props.onReject} />
      )}
    </section>
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
    maxTokenErrorRate: number;
    measuredRequests: number;
    measurementCoverage: number;
    savedCost: number;
    savedTokens: number;
    savingsRate: number;
    totalAudits: number;
  };
  copy: Copy;
  lastTelemetryRefresh: string;
  qualitySummary: QualitySummary | null;
  records: AuditRecord[];
}) {
  const quality = props.qualitySummary;

  return (
    <section className="tab-content active">
      <div className="db-grid">
        <DashboardCard icon={<Flame />} label={props.copy.dashboard.estimatedSavings} value={`${(props.aggregate.savingsRate * 100).toFixed(1)}%`} highlight />
        <DashboardCard icon={<Award />} label={props.copy.dashboard.savedTokens} value={`${Math.round(props.aggregate.savedTokens / 1000)}K`} />
        <DashboardCard icon={<Banknote />} label={props.copy.dashboard.savedUsd} value={`$${props.aggregate.savedCost.toFixed(2)}`} />
        <DashboardCard icon={<Database />} label={props.copy.dashboard.totalAudits} value={props.aggregate.totalAudits} />
        <DashboardCard icon={<ShieldCheck />} label={props.copy.dashboard.measuredCoverage} value={`${(props.aggregate.measurementCoverage * 100).toFixed(0)}%`} />
        <DashboardCard icon={<Activity />} label={props.copy.dashboard.avgTokenError} value={`${(props.aggregate.avgTokenErrorRate * 100).toFixed(1)}%`} />
      </div>

      <div className="telemetry-refresh-note">
        <RefreshCw size={12} />
        <span>{props.copy.dashboard.telemetryNote} {props.copy.status.lastSync}: {props.lastTelemetryRefresh}</span>
      </div>

      <div className="db-grid">
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
        <DashboardCard
          icon={<Sparkles />}
          label={props.copy.dashboard.overOptimization}
          value={quality?.over_optimization_count ?? "--"}
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

      <div className="chart-card">
        <div className="chart-title">{props.copy.dashboard.trend}</div>
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
            {props.copy.dashboard.recentActivity}
          </h3>
        </div>
        <div className="activity-list">
          {props.records.slice(0, 4).map((record) => (
            <div className="activity-row" key={record.id}>
              <span className={`activity-dot ${record.state}`} />
              <strong>{record.id}</strong>
              <span>{record.type}</span>
              <em>{(record.rate * 100).toFixed(0)}% {props.copy.dashboard.saved}</em>
            </div>
          ))}
        </div>
      </div>
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
          <span className={`badge badge-${props.record.state}`}>{props.record.state}</span>
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
