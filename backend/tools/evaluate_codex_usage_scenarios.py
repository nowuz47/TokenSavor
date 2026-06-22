from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrooge.optimizer import optimize_prompt  # noqa: E402
from scrooge.schemas import OptimizationMode, OptimizeRequest, TaskType  # noqa: E402


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    category: str
    expected_kind: str
    prompt: str
    task_type: TaskType | None = None
    must_preserve: tuple[str, ...] = ()


def repeated(line: str, count: int) -> str:
    return "\n".join([line] * count)


def numbered(prefix: str, count: int) -> str:
    return "\n".join(f"{prefix} {index}: value={index % 17}" for index in range(1, count + 1))


LONG_DIFF = "\n".join(
    [
        "diff --git a/src/payment.ts b/src/payment.ts",
        "@@ -12,7 +12,9 @@ export function authorize(order) {",
    ]
    + [f"- oldPaymentLine{i}();" for i in range(1, 80)]
    + [f"+ newPaymentLine{i}();" for i in range(1, 80)]
)

LONG_LOG = "\n".join(
    [
        "ERROR 12:04:15 payment.worker TimeoutError order_id=ORD-901 region=ap-northeast-2",
        "Traceback (most recent call last):",
        '  File "/app/payment/worker.py", line 88, in charge',
        "TimeoutError: gateway did not respond",
    ]
    * 140
)

CSV_SAMPLE = "\n".join(
    ["date,region,sku,revenue,orders,refund_rate"]
    + [f"2026-06-{(i % 28) + 1:02d},KR-{i % 5},SKU-{i % 12},{1000 + i * 7},{10 + i % 40},{(i % 9) / 100}" for i in range(240)]
)

JSON_SAMPLE = "{\n" + ",\n".join(
    f'  "event_{i}": {{"status": "{["ok", "warn", "error"][i % 3]}", "latency_ms": {80 + i}, "service": "checkout"}}'
    for i in range(180)
) + "\n}"


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("coding_01_calculator_app", "coding", "task_optimization", "Build a Python calculator app with parser tests, no eval(), decimal support, parentheses, and divide by zero handling.", TaskType.GENERAL, ("calculator", "eval", "divide by zero")),
    Scenario("coding_02_crud_api", "coding", "task_optimization", "Add CRUD API endpoints for projects in this FastAPI app. Include validation, errors, and tests.", TaskType.GENERAL, ("CRUD", "FastAPI", "tests")),
    Scenario("coding_03_react_filter_sort", "coding", "task_optimization", "Add filtering and sorting to the React dashboard table without changing existing columns.", TaskType.GENERAL, ("filtering", "sorting", "React")),
    Scenario("coding_04_function_option", "coding", "task_optimization", "Add an optional dry_run parameter to export_report and keep existing callers compatible.", TaskType.GENERAL, ("dry_run", "export_report")),
    Scenario("coding_05_cli_command", "coding", "task_optimization", "Add a CLI command named scrooge audit export that writes JSON and returns nonzero on failure.", TaskType.GENERAL, ("scrooge audit export", "JSON")),
    Scenario("coding_06_auth_middleware", "coding", "task_optimization", "Implement auth middleware for internal API routes and document how to test it.", TaskType.GENERAL, ("auth middleware", "test")),
    Scenario("coding_07_file_upload", "coding", "task_optimization", "Add text file upload support. Reject binary files and never store raw prompt bodies by default.", TaskType.GENERAL, ("text file", "binary", "raw prompt")),
    Scenario("coding_08_csv_import", "coding", "task_optimization", "Implement CSV import for orders with row-level validation and a preview before commit.", TaskType.GENERAL, ("CSV", "validation", "preview")),
    Scenario("coding_09_batch_job", "coding", "task_optimization", "Create a nightly batch job that aggregates token savings by team and writes summary rows.", TaskType.GENERAL, ("nightly", "team", "summary")),
    Scenario("coding_10_feature_flag", "coding", "task_optimization", "Add a feature flag for aggressive optimization and keep it disabled by default.", TaskType.GENERAL, ("feature flag", "disabled")),
    Scenario("debug_11_pytest_failure", "debugging", "task_optimization", "Pytest is failing in test_storage.py after the dashboard summary change. Find the root cause and fix it.", TaskType.BUG_ANALYSIS, ("test_storage.py", "dashboard summary")),
    Scenario("debug_12_python_stacktrace", "debugging", "token_saving", "Analyze this stack trace and propose a minimal fix:\n" + repeated('  File "/app/api.py", line 42, in handler\nValueError: invalid pricing_version', 90), TaskType.BUG_ANALYSIS, ("ValueError", "pricing_version")),
    Scenario("debug_13_typescript_build", "debugging", "token_saving", "Fix this TypeScript build output:\n" + repeated("src/App.tsx:42:13 - error TS2322: Type 'string' is not assignable to type 'number'.", 100), TaskType.BUG_ANALYSIS, ("TS2322", "src/App.tsx")),
    Scenario("debug_14_sqlite_migration", "debugging", "task_optimization", "SQLite migration fails on older scrooge.db files. Diagnose and make it backward compatible.", TaskType.BUG_ANALYSIS, ("SQLite", "backward compatible")),
    Scenario("debug_15_port_conflict", "debugging", "task_optimization", "The backend sidecar fails when port 8750 is occupied. Add detection and a clear user message.", TaskType.BUG_ANALYSIS, ("8750", "sidecar")),
    Scenario("debug_16_tray_close", "debugging", "task_optimization", "The tray app does not close cleanly when the daemon is running. Fix close, hide, and force quit behavior.", TaskType.BUG_ANALYSIS, ("tray", "force quit")),
    Scenario("debug_17_button_failure", "debugging", "task_optimization", "The optimize button sometimes says failed to fetch. Check frontend/backend integration and fix all broken buttons.", TaskType.BUG_ANALYSIS, ("failed to fetch", "buttons")),
    Scenario("debug_18_api_500", "debugging", "task_optimization", "POST /api/optimize returns 500 for Korean prompts with attachments. Find and fix the issue.", TaskType.BUG_ANALYSIS, ("POST /api/optimize", "Korean", "attachments")),
    Scenario("debug_19_race_condition", "debugging", "task_optimization", "There may be a race condition between hotkey capture and clipboard restore. Audit and fix if real.", TaskType.BUG_ANALYSIS, ("hotkey", "clipboard")),
    Scenario("debug_20_repro_steps", "debugging", "task_optimization", "Create a concise repro plan for dashboard values not updating after Ctrl+Alt+S.", TaskType.BUG_ANALYSIS, ("Ctrl+Alt+S", "dashboard")),
    Scenario("logs_21_cloudwatch_repeat", "logs", "token_saving", "Analyze these CloudWatch logs:\n" + LONG_LOG, TaskType.LOG_ANALYSIS, ("TimeoutError", "payment.worker")),
    Scenario("logs_22_error_1000", "logs", "token_saving", "Find the root cause in this production log:\n" + repeated("ERROR checkout failed status=503 retry=true service=payment", 1000), TaskType.LOG_ANALYSIS, ("503", "payment")),
    Scenario("logs_23_mixed_frequency", "logs", "token_saving", "Group these errors by frequency:\n" + "\n".join([repeated("ERROR auth invalid_token user=redacted", 180), repeated("WARN cache miss key=pricing", 90), repeated("ERROR payment timeout gateway=stripe", 40)]), TaskType.LOG_ANALYSIS, ("invalid_token", "payment timeout")),
    Scenario("logs_24_k8s_restart", "logs", "token_saving", "Analyze Kubernetes restart logs:\n" + repeated("pod/scrooge-backend CrashLoopBackOff last_state=OOMKilled container=scrooge", 220), TaskType.LOG_ANALYSIS, ("CrashLoopBackOff", "OOMKilled")),
    Scenario("logs_25_nginx_spike", "logs", "token_saving", "Summarize this nginx access spike:\n" + numbered("GET /api/dashboard/summary 200 latency_ms", 600), TaskType.LOG_ANALYSIS, ("nginx", "latency")),
    Scenario("logs_26_payment_timeout", "logs", "token_saving", "Payment timeout investigation:\n" + repeated("ERROR gateway timeout order_id=ORD-777 provider=toss elapsed_ms=30000", 300), TaskType.LOG_ANALYSIS, ("gateway timeout", "toss")),
    Scenario("logs_27_auth_failure", "logs", "token_saving", "Authentication failure logs:\n" + repeated("ERROR auth failed reason=expired_jwt tenant=enterprise-korea", 320), TaskType.LOG_ANALYSIS, ("expired_jwt", "enterprise-korea")),
    Scenario("logs_28_post_deploy", "logs", "token_saving", "After deployment, this error repeats:\n" + repeated("ERROR migration missing column request_attachments.optimized_tokens", 260), TaskType.LOG_ANALYSIS, ("request_attachments", "optimized_tokens")),
    Scenario("logs_29_slow_query", "logs", "token_saving", "Slow query log:\n" + repeated("WARN slow_query duration_ms=1840 query=dashboard_summary period=month", 260), TaskType.LOG_ANALYSIS, ("slow_query", "dashboard_summary")),
    Scenario("logs_30_retry_storm", "logs", "token_saving", "Worker retry storm:\n" + repeated("WARN retry attempt=5 queue=optimizer reason=upstream_429", 420), TaskType.LOG_ANALYSIS, ("upstream_429", "optimizer")),
    Scenario("refactor_31_mass_rename", "refactor", "task_optimization", "Plan a safe rename across 50 files from UsageRecord to AuditRecord without breaking public API.", TaskType.REFACTORING, ("UsageRecord", "AuditRecord")),
    Scenario("refactor_32_legacy_class", "refactor", "task_optimization", "Refactor the legacy TokenMeter class into pure functions while preserving behavior.", TaskType.REFACTORING, ("TokenMeter", "preserving behavior")),
    Scenario("refactor_33_js_to_ts", "refactor", "task_optimization", "Migrate the old dashboard JavaScript module to TypeScript with minimal churn.", TaskType.REFACTORING, ("TypeScript", "minimal churn")),
    Scenario("refactor_34_router_split", "refactor", "task_optimization", "Split FastAPI routes into optimize, audit, dashboard, and diagnostics routers.", TaskType.REFACTORING, ("FastAPI", "routers")),
    Scenario("refactor_35_react_state", "refactor", "task_optimization", "Simplify React state management in App.tsx without adding Redux.", TaskType.REFACTORING, ("App.tsx", "Redux")),
    Scenario("refactor_36_util_dedupe", "refactor", "task_optimization", "Find duplicate formatting utilities and consolidate them with tests.", TaskType.REFACTORING, ("formatting", "tests")),
    Scenario("refactor_37_deprecated_api", "refactor", "task_optimization", "Remove deprecated API fields while keeping old SQLite rows readable.", TaskType.REFACTORING, ("deprecated", "SQLite")),
    Scenario("refactor_38_db_migration", "refactor", "task_optimization", "Plan a database migration for attachment metrics with rollback and verification.", TaskType.REFACTORING, ("attachment metrics", "rollback")),
    Scenario("refactor_39_module_split", "refactor", "task_optimization", "Split the monolithic optimizer module into detector, compressor, and renderer modules.", TaskType.REFACTORING, ("optimizer", "compressor")),
    Scenario("refactor_40_config_change", "refactor", "task_optimization", "Change config loading to support environment variables and a local config file.", TaskType.REFACTORING, ("environment variables", "config file")),
    Scenario("test_41_pytest", "testing", "task_optimization", "Add pytest coverage for attachment unknown, estimated, and measured states.", TaskType.TEST_GENERATION, ("pytest", "attachment")),
    Scenario("test_42_react_testing", "testing", "task_optimization", "Add React Testing Library tests for dark mode, language switch, and empty trend state.", TaskType.TEST_GENERATION, ("React Testing Library", "dark mode")),
    Scenario("test_43_playwright_smoke", "testing", "task_optimization", "Create Playwright smoke tests for optimize button, audit tab, dashboard tab, and settings tab.", TaskType.TEST_GENERATION, ("Playwright", "dashboard")),
    Scenario("test_44_regression", "testing", "task_optimization", "Add regression tests for short prompts showing pass instead of fake savings.", TaskType.TEST_GENERATION, ("short prompts", "fake savings")),
    Scenario("test_45_edge_checklist", "testing", "task_optimization", "Create an edge-case checklist for Korean enterprise prompts and long logs.", TaskType.TEST_GENERATION, ("Korean", "long logs")),
    Scenario("test_46_failing_first", "testing", "task_optimization", "Write a failing test first for task optimization metrics, then implement the fix.", TaskType.TEST_GENERATION, ("failing test", "task optimization")),
    Scenario("test_47_snapshot_cleanup", "testing", "task_optimization", "Review snapshot tests and remove brittle snapshots that hide UI regressions.", TaskType.TEST_GENERATION, ("snapshot", "UI regressions")),
    Scenario("test_48_contract", "testing", "task_optimization", "Add API contract tests for OptimizeResponse and DashboardSummary fields.", TaskType.TEST_GENERATION, ("OptimizeResponse", "DashboardSummary")),
    Scenario("test_49_fixture", "testing", "task_optimization", "Replace mock-heavy tests with fixtures for logs, diffs, and CSV samples.", TaskType.TEST_GENERATION, ("fixtures", "CSV")),
    Scenario("test_50_installer_matrix", "testing", "task_optimization", "Build an installed-app smoke matrix for launch, tray, hotkey, backend, and uninstall.", TaskType.TEST_GENERATION, ("installed-app", "hotkey")),
    Scenario("review_51_pr_diff", "review_security", "token_saving", "Review this PR diff for correctness and regressions:\n" + LONG_DIFF, TaskType.CODE_REVIEW, ("payment.ts", "regressions")),
    Scenario("review_52_sql_injection", "review_security", "task_optimization", "Review SQL query construction for injection risk and suggest safe parameterization.", TaskType.CODE_REVIEW, ("SQL", "injection")),
    Scenario("review_53_secret_exposure", "review_security", "task_optimization", "Check whether audit logs could expose API keys, bearer tokens, or raw prompts.", TaskType.CODE_REVIEW, ("API keys", "raw prompts")),
    Scenario("review_54_eval", "review_security", "task_optimization", "Review calculator parser implementation and ensure eval is never used.", TaskType.CODE_REVIEW, ("calculator", "eval")),
    Scenario("review_55_auth_bypass", "review_security", "task_optimization", "Review auth middleware for bypass risk in internal admin endpoints.", TaskType.CODE_REVIEW, ("auth", "admin")),
    Scenario("review_56_permission_scope", "review_security", "task_optimization", "Review Tauri permissions and justify clipboard, shell sidecar, and global shortcut access.", TaskType.CODE_REVIEW, ("Tauri", "clipboard")),
    Scenario("review_57_dependency", "review_security", "task_optimization", "Review Python and npm dependencies for unnecessary packages and supply-chain risk.", TaskType.CODE_REVIEW, ("dependencies", "supply-chain")),
    Scenario("review_58_error_handling", "review_security", "task_optimization", "Review error handling so failed optimization never blocks the original user workflow.", TaskType.CODE_REVIEW, ("failed optimization", "workflow")),
    Scenario("review_59_privacy_logging", "review_security", "task_optimization", "Review logging privacy and ensure prompt bodies are not stored by default.", TaskType.CODE_REVIEW, ("privacy", "prompt bodies")),
    Scenario("review_60_installer_trust", "review_security", "task_optimization", "Review Windows installer trust posture, signing, Defender checks, and release notes.", TaskType.CODE_REVIEW, ("Windows", "Defender")),
    Scenario("data_61_csv_sales", "data", "token_saving", "Analyze this sales CSV for revenue trends and outliers:\n" + CSV_SAMPLE, TaskType.DATA_ANALYSIS, ("revenue", "outliers")),
    Scenario("data_62_json_schema", "data", "token_saving", "Summarize schema and error patterns in this JSON payload:\n" + JSON_SAMPLE, TaskType.DATA_ANALYSIS, ("schema", "error")),
    Scenario("data_63_sql_retention", "data", "task_optimization", "Write SQL to compute day-7 retention by signup_date using users and events tables.", TaskType.DATA_ANALYSIS, ("day-7", "signup_date")),
    Scenario("data_64_outlier", "data", "task_optimization", "Find possible outliers in daily token cost by team and explain validation checks.", TaskType.DATA_ANALYSIS, ("outliers", "team")),
    Scenario("data_65_funnel", "data", "task_optimization", "Analyze funnel drop-off from install to first hotkey optimization to accepted prompt.", TaskType.DATA_ANALYSIS, ("funnel", "hotkey")),
    Scenario("data_66_ab_test", "data", "task_optimization", "Summarize A/B test results comparing baseline, balanced, aggressive, and ML assisted.", TaskType.DATA_ANALYSIS, ("baseline", "ML assisted")),
    Scenario("data_67_dashboard_metrics", "data", "task_optimization", "Define dashboard metrics for token savings, task optimization, and measured coverage.", TaskType.DATA_ANALYSIS, ("token savings", "measured coverage")),
    Scenario("data_68_monthly_cost", "data", "task_optimization", "Analyze monthly AI cost trend and separate estimated from provider-measured usage.", TaskType.DATA_ANALYSIS, ("monthly", "provider-measured")),
    Scenario("data_69_team_aggregate", "data", "task_optimization", "Design team-level aggregation without individual surveillance.", TaskType.DATA_ANALYSIS, ("team-level", "surveillance")),
    Scenario("data_70_token_error", "data", "task_optimization", "Analyze token error rate by model and recommend when to trust local estimates.", TaskType.DATA_ANALYSIS, ("token error rate", "model")),
    Scenario("docs_71_architecture", "docs_planning", "task_optimization", "Review the Scrooge architecture and suggest production readiness improvements.", TaskType.ARCHITECTURE_REVIEW, ("architecture", "production")),
    Scenario("docs_72_mvp_plan", "docs_planning", "task_optimization", "Create an MVP execution plan for department pilot adoption.", TaskType.ARCHITECTURE_REVIEW, ("MVP", "pilot")),
    Scenario("docs_73_release_checklist", "docs_planning", "task_optimization", "Create a release checklist covering build, signing, install, smoke, and rollback.", TaskType.ARCHITECTURE_REVIEW, ("signing", "rollback")),
    Scenario("docs_74_runbook", "docs_planning", "task_optimization", "Write an incident runbook for backend sidecar failing to start.", TaskType.ARCHITECTURE_REVIEW, ("runbook", "sidecar")),
    Scenario("docs_75_onboarding", "docs_planning", "task_optimization", "Write a non-developer onboarding guide for using Ctrl+Alt+S safely.", TaskType.GENERAL, ("Ctrl+Alt+S", "non-developer")),
    Scenario("docs_76_agents", "docs_planning", "context_hygiene", "Optimize AGENTS.md so Codex gets only setup commands, test commands, style rules, and repo map.", TaskType.ARCHITECTURE_REVIEW, ("AGENTS.md", "test commands")),
    Scenario("docs_77_memory_files", "docs_planning", "context_hygiene", "Reduce CLAUDE.md and GEMINI.md always-on context. Split long reference material into on-demand files.", TaskType.ARCHITECTURE_REVIEW, ("CLAUDE.md", "GEMINI.md")),
    Scenario("docs_78_cursor_rules", "docs_planning", "context_hygiene", "Split Cursor rules by workflow so only relevant rules load for tests, UI, backend, and release.", TaskType.ARCHITECTURE_REVIEW, ("Cursor rules", "workflow")),
    Scenario("docs_79_human_audit", "docs_planning", "task_optimization", "Create a human audit checklist for prompt optimization quality and privacy review.", TaskType.ARCHITECTURE_REVIEW, ("audit checklist", "privacy")),
    Scenario("docs_80_rollout_gate", "docs_planning", "task_optimization", "Define rollout gates for department pilot, company-wide rollout, and billing-confirmed savings.", TaskType.ARCHITECTURE_REVIEW, ("department pilot", "billing-confirmed")),
)


def classify_result(response: Any) -> str:
    if response.saved_tokens > 0:
        return "token_saving"
    if response.optimization_mode == OptimizationMode.TASK_OPTIMIZATION:
        return "task_optimization"
    if response.optimized_tokens.input_tokens > response.original_tokens.input_tokens:
        return "pass_overhead"
    return "pass"


def pass_reason(response: Any) -> str:
    if response.saved_tokens > 0:
        return "input tokens reduced"
    if response.optimization_mode == OptimizationMode.TASK_OPTIMIZATION:
        return response.work_optimization_reason or "short broad request optimized for work path"
    if response.original_tokens.input_tokens <= 120:
        return "short prompt; rewriting would likely increase tokens"
    if response.optimized_tokens.input_tokens >= response.original_tokens.input_tokens:
        return "quality guard kept savings at zero because optimized prompt is not shorter"
    return "no safe token reduction found"


def preservation_passed(response: Any, scenario: Scenario) -> bool:
    optimized = response.optimized_prompt.lower()
    return all(term.lower() in optimized for term in scenario.must_preserve)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)

    category_summary = {}
    for category, items in sorted(by_category.items()):
        category_summary[category] = {
            "total": len(items),
            "actual_kind_counts": dict(Counter(item["actual_kind"] for item in items)),
            "expected_kind_counts": dict(Counter(item["expected_kind"] for item in items)),
            "preservation_pass_rate": round(
                sum(1 for item in items if item["preservation_passed"]) / len(items), 4
            ),
            "average_prompt_savings_rate": round(mean(item["savings_rate"] for item in items), 4),
            "average_overhead_tokens": round(mean(item["overhead_tokens"] for item in items), 2),
            "estimated_work_savings_minutes": sum(item["estimated_work_savings_minutes"] for item in items),
        }

    tokenizer_counts = dict(Counter(row["tokenizer_confidence"] for row in rows))
    return {
        "total": len(rows),
        "actual_kind_counts": dict(Counter(row["actual_kind"] for row in rows)),
        "expected_kind_counts": dict(Counter(row["expected_kind"] for row in rows)),
        "tokenizer_confidence_counts": tokenizer_counts,
        "preservation_pass_rate": round(sum(1 for row in rows if row["preservation_passed"]) / len(rows), 4),
        "average_prompt_savings_rate": round(mean(row["savings_rate"] for row in rows), 4),
        "token_saving_cases": sum(1 for row in rows if row["saved_tokens"] > 0),
        "task_optimization_cases": sum(1 for row in rows if row["actual_kind"] == "task_optimization"),
        "pass_overhead_cases": sum(1 for row in rows if row["actual_kind"] == "pass_overhead"),
        "total_original_tokens": sum(row["original_tokens"] for row in rows),
        "total_optimized_tokens": sum(row["optimized_tokens"] for row in rows),
        "total_saved_tokens": sum(row["saved_tokens"] for row in rows),
        "total_overhead_tokens": sum(row["overhead_tokens"] for row in rows),
        "estimated_work_savings_minutes": sum(row["estimated_work_savings_minutes"] for row in rows),
        "category_summary": category_summary,
    }


def recommendations(summary: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    if summary["token_saving_cases"] < summary["total"] * 0.25:
        notes.append(
            "Most Codex-style prompts are short or workflow-oriented. Treat token savings as a subset, not the main success metric."
        )
    if summary["pass_overhead_cases"] > summary["total"] * 0.25:
        notes.append(
            "Do not auto-rewrite short prompts. Offer task optimization as an explicit work-plan mode or paste only when the user accepts."
        )
    if summary["tokenizer_confidence_counts"].get("heuristic_fallback", 0):
        notes.append(
            "Install/use a model tokenizer or provider count endpoint. heuristic-v1 is useful for direction, but not billing-grade."
        )
    log_savings = summary["category_summary"].get("logs", {}).get("average_prompt_savings_rate", 0)
    if log_savings >= 0.2:
        notes.append("Prioritize logs, stack traces, diffs, CSV, and JSON attachments because they show real input-token reduction.")
    context_rows = [row for row in rows if row["expected_kind"] == "context_hygiene"]
    if context_rows:
        notes.append(
            "Add a context hygiene feature for AGENTS.md, CLAUDE.md, GEMINI.md, and Cursor rules. Always-on instructions are a better savings target than short chat prompts."
        )
    high_overhead = sorted(rows, key=lambda item: item["overhead_tokens"], reverse=True)[:5]
    if high_overhead:
        ids = ", ".join(item["scenario_id"] for item in high_overhead if item["overhead_tokens"] > 0)
        if ids:
            notes.append(f"Highest overhead cases should be pass-by-default or plan-only: {ids}.")
    return notes


def tokenizer_status() -> dict[str, Any]:
    tiktoken_available = importlib.util.find_spec("tiktoken") is not None
    return {
        "tiktoken_available": tiktoken_available,
        "measurement_grade": "local_model_tokenizer" if tiktoken_available else "heuristic_directional",
        "note": (
            "OpenAI-compatible local tokenizer is available."
            if tiktoken_available
            else "tiktoken is unavailable in this environment, so counts use heuristic-v1 and should not be treated as billing-grade."
        ),
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# Codex Usage Scenario Evaluation",
        "",
        f"Generated at: `{payload['generated_at']}`",
        f"Model: `{payload['model']}`",
        f"Tokenizer status: `{payload['tokenizer_status']['measurement_grade']}`",
        f"Tokenizer note: {payload['tokenizer_status']['note']}",
        "",
        "## Summary",
        "",
        f"- Total scenarios: {summary['total']}",
        f"- Token-saving cases: {summary['token_saving_cases']}",
        f"- Task-optimization cases: {summary['task_optimization_cases']}",
        f"- Pass with prompt overhead: {summary['pass_overhead_cases']}",
        f"- Preservation pass rate: {summary['preservation_pass_rate']:.1%}",
        f"- Average prompt savings rate: {summary['average_prompt_savings_rate']:.1%}",
        f"- Total original tokens: {summary['total_original_tokens']:,}",
        f"- Total optimized tokens: {summary['total_optimized_tokens']:,}",
        f"- Total saved tokens: {summary['total_saved_tokens']:,}",
        f"- Total overhead tokens: {summary['total_overhead_tokens']:,}",
        f"- Estimated work savings: {summary['estimated_work_savings_minutes']} minutes",
        f"- Tokenizer confidence: `{summary['tokenizer_confidence_counts']}`",
        "",
        "## Category Summary",
        "",
        "| Category | Total | Actual kinds | Avg savings | Avg overhead | Work saved min | Preservation |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for category, item in summary["category_summary"].items():
        lines.append(
            f"| {category} | {item['total']} | `{item['actual_kind_counts']}` | "
            f"{item['average_prompt_savings_rate']:.1%} | {item['average_overhead_tokens']:.1f} | "
            f"{item['estimated_work_savings_minutes']} | {item['preservation_pass_rate']:.1%} |"
        )
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {note}" for note in payload["recommendations"])
    lines.extend(["", "## Scenario Results", ""])
    lines.append("| ID | Category | Expected | Actual | Original | Optimized | Saved | Overhead | Reason |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |")
    for row in payload["rows"]:
        lines.append(
            f"| {row['scenario_id']} | {row['category']} | {row['expected_kind']} | {row['actual_kind']} | "
            f"{row['original_tokens']} | {row['optimized_tokens']} | {row['saved_tokens']} | "
            f"{row['overhead_tokens']} | {row['pass_reason']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Scrooge against Codex-style usage scenarios.")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "reports"))
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        response = optimize_prompt(
            OptimizeRequest(
                prompt=scenario.prompt,
                provider=args.provider,
                model=args.model,
                task_type=scenario.task_type,
            )
        )
        original = response.original_tokens.input_tokens
        optimized = response.optimized_tokens.input_tokens
        rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "category": scenario.category,
                "expected_kind": scenario.expected_kind,
                "actual_kind": classify_result(response),
                "task_type": response.task_type.value,
                "optimization_mode": response.optimization_mode.value,
                "original_tokens": original,
                "optimized_tokens": optimized,
                "saved_tokens": response.saved_tokens,
                "savings_rate": response.savings_rate,
                "overhead_tokens": max(0, optimized - original),
                "estimated_work_savings_minutes": response.estimated_work_savings_minutes,
                "estimated_followup_reduction": response.estimated_followup_reduction,
                "tokenizer": response.optimized_tokens.tokenizer,
                "tokenizer_confidence": response.optimized_tokens.tokenizer_confidence.value,
                "preservation_passed": preservation_passed(response, scenario),
                "pass_reason": pass_reason(response),
                "applied_rules": [reason.rule_id for reason in response.reasons],
            }
        )

    summary = summarize(rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": args.provider,
        "model": args.model,
        "tokenizer_status": tokenizer_status(),
        "summary": summary,
        "recommendations": recommendations(summary, rows),
        "rows": rows,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"codex-scenario-evaluation-{stamp}.json"
    md_path = out_dir / f"codex-scenario-evaluation-{stamp}.md"
    latest_json = out_dir / "codex-scenario-evaluation-latest.json"
    latest_md = out_dir / "codex-scenario-evaluation-latest.md"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    latest_json.write_text(json_text + "\n", encoding="utf-8")
    write_markdown(md_path, payload)
    write_markdown(latest_md, payload)

    print(json.dumps({"summary": summary, "recommendations": payload["recommendations"], "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
