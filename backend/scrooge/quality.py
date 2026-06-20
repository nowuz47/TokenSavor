from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from statistics import mean

from scrooge.optimizer import optimize_prompt
from scrooge.schemas import OptimizeRequest, OptimizeResponse, TaskType


class QualityCategory(StrEnum):
    CODING = "coding"
    DEBUGGING = "debugging"
    LOGS = "logs"
    DATA = "data"
    DOCS_PLANNING = "docs_planning"


@dataclass(frozen=True)
class GoldenPrompt:
    name: str
    category: QualityCategory
    prompt: str
    task_type: TaskType
    must_preserve: tuple[str, ...]
    must_not_add: tuple[str, ...] = ()
    expected_behavior: tuple[str, ...] = ()
    min_savings_rate: float = 0
    short_prompt: bool = False


@dataclass(frozen=True)
class QualityResult:
    name: str
    category: QualityCategory
    passed: bool
    preservation_passed: bool
    behavior_passed: bool
    hallucination_passed: bool
    savings_passed: bool
    savings_rate: float
    missing_terms: tuple[str, ...]
    missing_behaviors: tuple[str, ...]
    hallucinated_terms: tuple[str, ...]
    optimized_tokens: int
    original_tokens: int
    short_prompt: bool
    over_optimized: bool


@dataclass(frozen=True)
class CategoryQualitySummary:
    category: QualityCategory
    total_cases: int
    passed_cases: int
    preservation_pass_rate: float
    average_savings_rate: float
    harmful_omission_count: int
    hallucinated_constraint_count: int
    over_optimization_count: int
    savings_floor_failures: int


@dataclass(frozen=True)
class QualityReport:
    total_cases: int
    passed_cases: int
    quality_preservation_rate: float
    average_savings_rate: float
    harmful_omission_count: int
    hallucinated_constraint_count: int
    over_optimization_count: int
    category_summaries: tuple[CategoryQualitySummary, ...]
    results: tuple[QualityResult, ...]


def repeated(lines: list[str], count: int) -> list[str]:
    return [line for _ in range(count) for line in lines]


GOLDEN_PROMPTS: tuple[GoldenPrompt, ...] = (
    GoldenPrompt(
        name="coding_calculator_app",
        category=QualityCategory.CODING,
        task_type=TaskType.GENERAL,
        must_preserve=("HTML", "CSS", "JavaScript", "divide by zero", "eval()"),
        must_not_add=("React", "serverless", "Docker"),
        expected_behavior=("Goal:", "User request/context:"),
        short_prompt=True,
        prompt="\n".join(
            [
                "Build a browser calculator app with HTML, CSS, and JavaScript.",
                "Support parentheses, negative numbers, decimals, exponentiation, and divide by zero errors.",
                "Add Node tests for parser precedence and invalid input.",
                "The old prototype used eval(), which is not allowed.",
                "The old prototype used eval(), which is not allowed.",
            ]
        ),
    ),
    GoldenPrompt(
        name="coding_refactor_parser",
        category=QualityCategory.CODING,
        task_type=TaskType.REFACTORING,
        must_preserve=("parser.py", "parse_expression", "no behavior changes"),
        must_not_add=("rewrite in Rust", "database migration"),
        expected_behavior=("Refactor", "preserving behavior", "tests"),
        short_prompt=True,
        prompt=(
            "Refactor parser.py parse_expression to reduce duplication with no behavior changes. "
            "Keep public function names stable and list tests to run."
        ),
    ),
    GoldenPrompt(
        name="coding_test_generation",
        category=QualityCategory.CODING,
        task_type=TaskType.TEST_GENERATION,
        must_preserve=("pytest", "discount_code", "expired coupon", "boundary"),
        must_not_add=("Playwright", "real payment gateway"),
        expected_behavior=("test cases", "edge cases"),
        short_prompt=True,
        prompt=(
            "Generate pytest cases for checkout.py discount_code handling, including expired coupon, "
            "empty code, percent discount boundary, and fixed amount boundary."
        ),
    ),
    GoldenPrompt(
        name="coding_security_review_diff",
        category=QualityCategory.CODING,
        task_type=TaskType.CODE_REVIEW,
        must_preserve=("diff --git", "@@", "auth.py", "return True"),
        must_not_add=("OAuth migration", "Kubernetes"),
        expected_behavior=("findings first", "security"),
        prompt="\n".join(
            [
                "Please review this diff for regressions.",
                "diff --git a/auth.py b/auth.py",
                "@@ -10,7 +10,7 @@",
                "- return user.is_admin",
                "+ return True",
            ]
        ),
    ),
    GoldenPrompt(
        name="coding_large_diff",
        category=QualityCategory.CODING,
        task_type=TaskType.CODE_REVIEW,
        must_preserve=("diff --git", "@@", "billing.py", "amount_cents"),
        must_not_add=("schema migration", "Stripe webhook"),
        expected_behavior=("findings first", "missing tests"),
        min_savings_rate=0.2,
        prompt="\n".join(
            [
                "Review this billing diff for correctness and missing tests.",
                "diff --git a/billing.py b/billing.py",
                "@@ -80,7 +80,7 @@",
            ]
            + repeated(["- amount_cents = price * 100", "+ amount_cents = int(price) * 100"], 90)
        ),
    ),
    GoldenPrompt(
        name="coding_mobile_ui_fix",
        category=QualityCategory.CODING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("mobile viewport", "display overflow", "calculator.css"),
        must_not_add=("Tailwind", "build pipeline"),
        expected_behavior=("Root cause", "Fix plan"),
        short_prompt=True,
        prompt=(
            "Bug: calculator.css display overflows on mobile viewport when result has many digits. "
            "Find cause and propose minimal CSS fix without adding a new build step."
        ),
    ),
    GoldenPrompt(
        name="coding_cli_error_handling",
        category=QualityCategory.CODING,
        task_type=TaskType.REFACTORING,
        must_preserve=("cli.py", "ValueError", "--json"),
        must_not_add=("REST API", "PostgreSQL"),
        expected_behavior=("compatibility risks", "tests"),
        short_prompt=True,
        prompt="Refactor cli.py so ValueError messages are consistent, but keep --json output stable.",
    ),
    GoldenPrompt(
        name="coding_node_parser_tests",
        category=QualityCategory.CODING,
        task_type=TaskType.TEST_GENERATION,
        must_preserve=("Node", "unary minus", "exponent associativity"),
        must_not_add=("browser automation", "snapshot tests"),
        expected_behavior=("fixtures", "edge cases"),
        short_prompt=True,
        prompt="Add Node tests for calculator parser unary minus, exponent associativity, and invalid input.",
    ),
    GoldenPrompt(
        name="coding_api_contract_review",
        category=QualityCategory.CODING,
        task_type=TaskType.CODE_REVIEW,
        must_preserve=("MeasurementResponse", "token_error_rate", "request_id"),
        must_not_add=("GraphQL", "Kafka"),
        expected_behavior=("regressions", "file/line"),
        short_prompt=True,
        prompt="Review MeasurementResponse changes for API compatibility: request_id and token_error_rate must remain.",
    ),
    GoldenPrompt(
        name="coding_small_task_no_overopt",
        category=QualityCategory.CODING,
        task_type=TaskType.GENERAL,
        must_preserve=("README", "installation command"),
        must_not_add=("CI deployment", "release notes"),
        expected_behavior=("Goal:", "assumptions"),
        short_prompt=True,
        prompt="Update README with the installation command and keep it short.",
    ),
    GoldenPrompt(
        name="debug_parser_error",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("ParserError", "config.py", "line 45"),
        must_not_add=("network outage", "database lock"),
        expected_behavior=("Root cause", "Fix plan"),
        prompt="\n".join(
            [
                "Find the bug cause.",
                'File "/app/scrooge/config.py", line 45, in parse_yaml',
                "yaml.parser.ParserError: expected '<document start>'",
                "yaml.parser.ParserError: expected '<document start>'",
            ]
        ),
    ),
    GoldenPrompt(
        name="debug_stacktrace_payment",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("charge_card", "PaymentTimeout", "line 88"),
        must_not_add=("refund", "data corruption"),
        expected_behavior=("Root cause", "Tests to run"),
        prompt="\n".join(
            [
                "Traceback (most recent call last):",
                'File "/srv/payments.py", line 88, in charge_card',
                "PaymentTimeout: upstream gateway did not respond",
                "PaymentTimeout: upstream gateway did not respond",
            ]
        ),
    ),
    GoldenPrompt(
        name="debug_repro_steps",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("Windows ARM64", "tauri build", "link.exe"),
        must_not_add=("Linux", "Docker"),
        expected_behavior=("Root cause", "Fix plan"),
        short_prompt=True,
        prompt="On Windows ARM64, tauri build fails because link.exe is missing. Give repro steps and checks.",
    ),
    GoldenPrompt(
        name="debug_ui_state",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("Dashboard", "measured", "estimated"),
        must_not_add=("authentication", "multi-tenant"),
        expected_behavior=("Impact/risk", "Tests to run"),
        short_prompt=True,
        prompt="Bug: Dashboard labels measured records as estimated after refresh. Preserve measured vs estimated distinction.",
    ),
    GoldenPrompt(
        name="debug_sqlite_missing",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("sqlite", "scrooge.db", "no such table"),
        must_not_add=("Redis", "S3"),
        expected_behavior=("Root cause", "Fix plan"),
        short_prompt=True,
        prompt="After deleting scrooge.db, startup raises sqlite no such table audit_records. Find the safe fix.",
    ),
    GoldenPrompt(
        name="debug_pytest_import",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("pytest", "ModuleNotFoundError", "tools"),
        must_not_add=("pip uninstall", "rename package"),
        expected_behavior=("Root cause", "Tests to run"),
        short_prompt=True,
        prompt="pytest from repo root fails with ModuleNotFoundError: tools in backend/tests/test_calculator_validation.py.",
    ),
    GoldenPrompt(
        name="debug_proxy_port_conflict",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("127.0.0.1:8750", "another process", "port"),
        must_not_add=("public bind", "0.0.0.0"),
        expected_behavior=("Root cause", "Fix plan"),
        short_prompt=True,
        prompt="Scrooge sidecar cannot bind 127.0.0.1:8750 because another process owns the port.",
    ),
    GoldenPrompt(
        name="debug_token_math",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("saved_tokens", "max(0", "optimized_tokens"),
        must_not_add=("negative savings", "manual override"),
        expected_behavior=("Root cause", "Fix plan"),
        short_prompt=True,
        prompt="Check saved_tokens formula: it must be max(0, original_tokens - optimized_tokens).",
    ),
    GoldenPrompt(
        name="debug_long_stacktrace",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("ValueError", "normalize_prompt", "line 132"),
        must_not_add=("database outage", "memory leak"),
        expected_behavior=("Root cause", "Impact/risk"),
        min_savings_rate=0.2,
        prompt="\n".join(
            ["Investigate this repeated stack trace."]
            + repeated(
                [
                    'File "/app/scrooge/optimizer.py", line 132, in normalize_prompt',
                    "ValueError: invalid template marker",
                ],
                80,
            )
        ),
    ),
    GoldenPrompt(
        name="debug_failed_measurement",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("MeasurementRequest", "measured_input_tokens", "422"),
        must_not_add=("OAuth", "rate limit"),
        expected_behavior=("Root cause", "Tests to run"),
        short_prompt=True,
        prompt="POST MeasurementRequest returns 422 when measured_input_tokens is missing. Explain cause and test.",
    ),
    GoldenPrompt(
        name="logs_payment_cloudwatch",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("payment-service", "timeout", "Traceback"),
        must_not_add=("auth-service", "disk full"),
        expected_behavior=("top signals", "suspected cause"),
        prompt="\n".join(
            [
                "CloudWatch logs from payment-service:",
                "ERROR payment-service timeout while charging card",
                "ERROR payment-service timeout while charging card",
                "Traceback (most recent call last):",
                "Exception: upstream timeout",
            ]
        ),
    ),
    GoldenPrompt(
        name="logs_long_payment",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("payment-service", "timeout", "upstream timeout"),
        must_not_add=("cache miss", "deploy rollback"),
        expected_behavior=("top signals", "suspected cause"),
        min_savings_rate=0.2,
        prompt="\n".join(
            ["Analyze these production logs and keep the key error pattern."]
            + [
                "ERROR payment-service timeout while charging card request_id=12345 user_id=7788"
                for _ in range(120)
            ]
            + ["Traceback (most recent call last):", "Exception: upstream timeout"]
        ),
    ),
    GoldenPrompt(
        name="logs_mixed_errors",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("inventory-service", "deadlock", "sku=ABC-42"),
        must_not_add=("payment-service", "OOM"),
        expected_behavior=("top signals", "next checks"),
        min_savings_rate=0.2,
        prompt="\n".join(
            ["Analyze app logs and group repeated failures."]
            + repeated(
                [
                    "ERROR inventory-service deadlock while reserving sku=ABC-42",
                    "WARN inventory-service retry succeeded sku=ABC-42",
                ],
                70,
            )
        ),
    ),
    GoldenPrompt(
        name="logs_access_spike",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("GET /api/checkout", "503", "10:05"),
        must_not_add=("SQL injection", "bot attack"),
        expected_behavior=("top signals", "remediation"),
        prompt="\n".join(
            [
                "Access log anomaly:",
                "10:05 GET /api/checkout 503 1200ms",
                "10:05 GET /api/checkout 503 1180ms",
                "10:06 GET /api/checkout 200 90ms",
            ]
        ),
    ),
    GoldenPrompt(
        name="logs_stacktrace_frame_limit",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("Traceback", "KeyError", "customer_id"),
        must_not_add=("ValueError", "timeout"),
        expected_behavior=("top signals", "suspected cause"),
        prompt="\n".join(
            [
                "Traceback (most recent call last):",
                'File "/app/report.py", line 30, in build',
                "KeyError: customer_id",
            ]
            + repeated(['File "/app/report.py", line 30, in build'], 40)
        ),
    ),
    GoldenPrompt(
        name="logs_short_noisy",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("worker-7", "job_id=9001", "retry exhausted"),
        must_not_add=("network partition", "database migration"),
        expected_behavior=("top signals", "next checks"),
        short_prompt=True,
        prompt="ERROR worker-7 retry exhausted job_id=9001. What should I check next?",
    ),
    GoldenPrompt(
        name="logs_batch_failure",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("batch-loader", "S3AccessDenied", "bucket=scrooge-prod"),
        must_not_add=("local disk", "CPU saturation"),
        expected_behavior=("suspected cause", "remediation"),
        prompt="\n".join(
            [
                "ERROR batch-loader S3AccessDenied bucket=scrooge-prod",
                "ERROR batch-loader S3AccessDenied bucket=scrooge-prod",
                "INFO batch-loader retry=1",
            ]
        ),
    ),
    GoldenPrompt(
        name="logs_latency_regression",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("p95", "checkout", "4200ms"),
        must_not_add=("memory leak", "auth failure"),
        expected_behavior=("top signals", "next checks"),
        short_prompt=True,
        prompt="checkout p95 latency jumped to 4200ms after deploy. Logs show slow query warnings.",
    ),
    GoldenPrompt(
        name="logs_service_restart",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("api-gateway", "SIGTERM", "pod=scrooge-api-17"),
        must_not_add=("payment timeout", "certificate expired"),
        expected_behavior=("suspected cause", "remediation"),
        prompt="\n".join(
            [
                "WARN api-gateway received SIGTERM pod=scrooge-api-17",
                "INFO api-gateway graceful shutdown started",
                "WARN api-gateway received SIGTERM pod=scrooge-api-17",
            ]
        ),
    ),
    GoldenPrompt(
        name="logs_frequency_summary",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("email-service", "SMTPTimeout", "message_id"),
        must_not_add=("SMS provider", "template syntax"),
        expected_behavior=("top signals", "suspected cause"),
        min_savings_rate=0.2,
        prompt="\n".join(
            ["Count repeated failures."]
            + [
                f"ERROR email-service SMTPTimeout message_id={1000 + index}"
                for index in range(150)
            ]
        ),
    ),
    GoldenPrompt(
        name="coding_korean_calculator",
        category=QualityCategory.CODING,
        task_type=TaskType.GENERAL,
        must_preserve=("파이썬", "eval()", "0으로 나누기", "pytest"),
        must_not_add=("React", "Docker", "클라우드 배포"),
        expected_behavior=("Goal:", "User request/context:"),
        short_prompt=True,
        prompt=(
            "계산기 앱을 파이썬으로 만들어주세요. eval()은 쓰지 말고, "
            "덧셈/뺄셈/곱셈/나눗셈과 0으로 나누기 예외 처리를 포함해 주세요. "
            "pytest 테스트도 같이 작성해 주세요."
        ),
    ),
    GoldenPrompt(
        name="debugging_korean_hotkey_dashboard",
        category=QualityCategory.DEBUGGING,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("Ctrl+Alt+S", "대시보드", "SQLite audit record"),
        must_not_add=("로그인", "권한 서버", "클라우드 동기화"),
        expected_behavior=("Root cause", "Fix plan"),
        short_prompt=True,
        prompt=(
            "Tauri 앱에서 단축키 Ctrl+Alt+S를 눌러도 대시보드의 사용 로그와 "
            "절감 토큰이 바로 반영되지 않습니다. 이벤트 emit, frontend refresh, "
            "SQLite audit record 저장 여부를 기준으로 원인과 수정안을 제시해 주세요."
        ),
    ),
    GoldenPrompt(
        name="logs_korean_payment_repeated",
        category=QualityCategory.LOGS,
        task_type=TaskType.LOG_ANALYSIS,
        must_preserve=("payment-api", "KCP", "배포 직후 5분"),
        must_not_add=("인증 장애", "디스크 부족", "개인정보 유출"),
        expected_behavior=("top signals", "suspected cause"),
        min_savings_rate=0.2,
        prompt="\n".join(
            ["아래 운영 로그를 분석해서 장애 원인, 영향 범위, 즉시 조치, 재발 방지책을 정리해 주세요."]
            + repeated(
                ["2026-06-20 09:01:11 ERROR payment-api timeout order_id=1001 pg=KCP latency=5300ms"],
                60,
            )
            + ["CloudWatch 기준이며 배포 직후 5분 동안만 발생했습니다."]
        ),
    ),
    GoldenPrompt(
        name="data_korean_sales_report",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("sales_2026_q1.csv", "business_unit", "region", "전년 동기 대비 15%"),
        must_not_add=("고객 PII", "머신러닝 필수", "원본 업로드"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt=(
            "sales_2026_q1.csv를 분석해서 사업부, 지역, 상품군별 매출 증감률을 구하고, "
            "전년 동기 대비 15% 이상 하락한 항목을 찾아주세요. 컬럼은 business_unit, "
            "region, product, revenue, year, quarter 입니다. 결과는 임원 보고용 요약과 SQL 예시를 함께 주세요."
        ),
    ),
    GoldenPrompt(
        name="docs_korean_enterprise_trust",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.ARCHITECTURE_REVIEW,
        must_preserve=("한국 대기업", "팀 단위 통계", "원문 프롬프트 저장 금지"),
        must_not_add=("개인별 순위", "원문 중앙 저장", "자동 전송"),
        expected_behavior=("recommendation", "risks"),
        short_prompt=True,
        prompt=(
            "한국 대기업 사내 도입 기준으로 Scrooge 신뢰 정책을 정리해 주세요. "
            "팀 단위 통계, 원문 프롬프트 저장 금지, 가격표 버전 추적, 실측/추정 구분을 포함해야 합니다."
        ),
    ),
    GoldenPrompt(
        name="data_csv_revenue",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("revenue.csv", "region", "net_revenue", "2026-Q1"),
        must_not_add=("machine learning", "customer PII"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt="Analyze revenue.csv for 2026-Q1 by region and net_revenue. Show top declines.",
    ),
    GoldenPrompt(
        name="data_sql_retention",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("users", "events", "retention_day_7", "signup_date"),
        must_not_add=("payments", "email export"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt="Write SQL joining users and events to compute retention_day_7 grouped by signup_date.",
    ),
    GoldenPrompt(
        name="data_json_anomaly",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("events.json", "latency_ms", "service", "p99"),
        must_not_add=("financial forecast", "GPU"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt="From events.json, find service-level p99 latency_ms anomalies and explain likely drivers.",
    ),
    GoldenPrompt(
        name="data_stat_summary",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("mean", "median", "stddev", "order_value"),
        must_not_add=("causal inference", "A/B test"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt="Summarize order_value with mean, median, stddev, min, max, and outliers.",
    ),
    GoldenPrompt(
        name="data_sql_cost",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("cloud_costs", "team", "month", "usd"),
        must_not_add=("invoice download", "currency conversion"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt="Create a SQL query over cloud_costs to aggregate usd by team and month.",
    ),
    GoldenPrompt(
        name="data_csv_long_context",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("customer_id", "churn_score", "plan", "enterprise"),
        must_not_add=("credit card", "HIPAA"),
        expected_behavior=("validation checks", "method/query"),
        min_savings_rate=0.2,
        prompt="\n".join(
            ["Analyze CSV rows and identify enterprise churn risk drivers.", "customer_id,plan,churn_score,reason"]
            + [
                f"C{1000 + index},enterprise,0.91,usage dropped"
                for index in range(120)
            ]
        ),
    ),
    GoldenPrompt(
        name="data_metric_definition",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("activation_rate", "activated_at", "created_at"),
        must_not_add=("revenue", "subscription"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt="Define activation_rate using activated_at and created_at, then suggest validation checks.",
    ),
    GoldenPrompt(
        name="data_experiment_readout",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("variant", "conversion_rate", "confidence interval"),
        must_not_add=("Bayesian", "user emails"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt="Analyze A/B test results by variant, conversion_rate, and confidence interval.",
    ),
    GoldenPrompt(
        name="data_dashboard_bug",
        category=QualityCategory.DATA,
        task_type=TaskType.BUG_ANALYSIS,
        must_preserve=("dashboard", "saved_cost_usd", "rounding"),
        must_not_add=("exchange rate", "tax"),
        expected_behavior=("Root cause", "Fix plan"),
        short_prompt=True,
        prompt="Dashboard saved_cost_usd appears off by rounding. Find the calculation issue.",
    ),
    GoldenPrompt(
        name="data_outlier_detection",
        category=QualityCategory.DATA,
        task_type=TaskType.DATA_ANALYSIS,
        must_preserve=("z-score", "latency_ms", "service_name"),
        must_not_add=("deep learning", "anomaly API"),
        expected_behavior=("validation checks", "method/query"),
        short_prompt=True,
        prompt="Use z-score to flag latency_ms outliers grouped by service_name.",
    ),
    GoldenPrompt(
        name="docs_architecture_review",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.ARCHITECTURE_REVIEW,
        must_preserve=("local-first", "SQLite", "pricing version"),
        must_not_add=("cloud mandatory", "raw prompt upload"),
        expected_behavior=("recommendation", "alternatives", "risks"),
        short_prompt=True,
        prompt="Review Scrooge architecture: local-first SQLite audit logs and pricing version traceability.",
    ),
    GoldenPrompt(
        name="docs_rollout_plan",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.ARCHITECTURE_REVIEW,
        must_preserve=("5 developers", "2 weeks", "20 users"),
        must_not_add=("company-wide launch", "mandatory monitoring"),
        expected_behavior=("rollout notes", "risks"),
        short_prompt=True,
        prompt="Create pilot rollout plan: 5 developers for 2 weeks, then 20 users for 4 weeks.",
    ),
    GoldenPrompt(
        name="docs_requirements_summary",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.GENERAL,
        must_preserve=("estimated", "sent", "measured"),
        must_not_add=("person-level ranking", "raw prompt storage"),
        expected_behavior=("concise", "assumptions"),
        short_prompt=True,
        prompt="Summarize requirements for estimated, sent, and measured usage states.",
    ),
    GoldenPrompt(
        name="docs_trust_policy",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.ARCHITECTURE_REVIEW,
        must_preserve=("team-level", "hash", "local storage"),
        must_not_add=("employee surveillance", "raw code upload"),
        expected_behavior=("risks", "recommendation"),
        short_prompt=True,
        prompt="Draft trust policy: team-level metrics, prompt hash only, local storage by default.",
    ),
    GoldenPrompt(
        name="docs_api_design",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.ARCHITECTURE_REVIEW,
        must_preserve=("/api/optimize", "/api/dashboard/summary", "AuditRecordSummary"),
        must_not_add=("GraphQL", "public API key"),
        expected_behavior=("alternatives", "risks"),
        short_prompt=True,
        prompt="Review API design for /api/optimize, /api/dashboard/summary, and AuditRecordSummary.",
    ),
    GoldenPrompt(
        name="docs_release_checklist",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.GENERAL,
        must_preserve=("pytest", "frontend build", "quality gate"),
        must_not_add=("production deploy", "cloud backup"),
        expected_behavior=("actionable", "assumptions"),
        short_prompt=True,
        prompt="Make release checklist with pytest, frontend build, quality gate, and calculator validation.",
    ),
    GoldenPrompt(
        name="docs_sidecar_lifecycle",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.ARCHITECTURE_REVIEW,
        must_preserve=("sidecar", "127.0.0.1:8750", "tray"),
        must_not_add=("remote server", "admin service"),
        expected_behavior=("risks", "rollout notes"),
        short_prompt=True,
        prompt="Document sidecar lifecycle: start backend on 127.0.0.1:8750 and keep app in tray.",
    ),
    GoldenPrompt(
        name="docs_failure_modes",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.ARCHITECTURE_REVIEW,
        must_preserve=("port conflict", "SQLite deletion", "backend unavailable"),
        must_not_add=("cloud failover", "auto billing"),
        expected_behavior=("risks", "recommendation"),
        short_prompt=True,
        prompt="List MVP failure modes: port conflict, SQLite deletion, backend unavailable.",
    ),
    GoldenPrompt(
        name="docs_human_audit",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.GENERAL,
        must_preserve=("10%", "20%", "blind review"),
        must_not_add=("individual scorecard", "manager alert"),
        expected_behavior=("assumptions", "actionable"),
        short_prompt=True,
        prompt="Define human audit sample: 10% to 20% blind review of optimized prompts.",
    ),
    GoldenPrompt(
        name="docs_ml_assisted_policy",
        category=QualityCategory.DOCS_PLANNING,
        task_type=TaskType.ARCHITECTURE_REVIEW,
        must_preserve=("ML assisted", "generate candidates", "validator"),
        must_not_add=("auto-send", "unreviewed prompt"),
        expected_behavior=("recommendation", "risks"),
        short_prompt=True,
        prompt="Policy: ML assisted can generate candidates, but validator must pass before use.",
    ),
)


def evaluate_golden_prompt(
    golden: GoldenPrompt,
    provider: str = "openai",
    model: str = "gpt-5.4-mini",
) -> QualityResult:
    response = optimize_prompt(
        OptimizeRequest(
            prompt=golden.prompt,
            provider=provider,
            model=model,
            task_type=golden.task_type,
        )
    )
    return evaluate_response(golden, response)


def evaluate_response(golden: GoldenPrompt, response: OptimizeResponse) -> QualityResult:
    optimized = response.optimized_prompt.lower()
    missing_terms = tuple(term for term in golden.must_preserve if term.lower() not in optimized)
    missing_behaviors = tuple(
        term for term in golden.expected_behavior if term.lower() not in optimized
    )
    hallucinated_terms = tuple(
        term for term in golden.must_not_add if term.lower() in optimized
    )
    preservation_passed = not missing_terms
    behavior_passed = not missing_behaviors
    hallucination_passed = not hallucinated_terms
    savings_passed = response.savings_rate >= golden.min_savings_rate
    over_optimized = golden.short_prompt and (
        not preservation_passed or not behavior_passed or not hallucination_passed
    )
    passed = (
        preservation_passed
        and behavior_passed
        and hallucination_passed
        and savings_passed
        and not over_optimized
    )

    return QualityResult(
        name=golden.name,
        category=golden.category,
        passed=passed,
        preservation_passed=preservation_passed,
        behavior_passed=behavior_passed,
        hallucination_passed=hallucination_passed,
        savings_passed=savings_passed,
        savings_rate=response.savings_rate,
        missing_terms=missing_terms,
        missing_behaviors=missing_behaviors,
        hallucinated_terms=hallucinated_terms,
        original_tokens=response.original_tokens.input_tokens,
        optimized_tokens=response.optimized_tokens.input_tokens,
        short_prompt=golden.short_prompt,
        over_optimized=over_optimized,
    )


def evaluate_golden_suite(
    provider: str = "openai",
    model: str = "gpt-5.4-mini",
) -> list[QualityResult]:
    return [evaluate_golden_prompt(item, provider, model) for item in GOLDEN_PROMPTS]


def summarize_quality_results(results: list[QualityResult]) -> QualityReport:
    category_summaries = tuple(
        _summarize_category(category, results)
        for category in QualityCategory
        if any(result.category == category for result in results)
    )
    passed_cases = sum(1 for result in results if result.passed)
    return QualityReport(
        total_cases=len(results),
        passed_cases=passed_cases,
        quality_preservation_rate=round(passed_cases / len(results), 4) if results else 0,
        average_savings_rate=round(mean(result.savings_rate for result in results), 4)
        if results
        else 0,
        harmful_omission_count=sum(len(result.missing_terms) for result in results),
        hallucinated_constraint_count=sum(
            len(result.hallucinated_terms) for result in results
        ),
        over_optimization_count=sum(1 for result in results if result.over_optimized),
        category_summaries=category_summaries,
        results=tuple(results),
    )


def evaluate_quality_report(
    provider: str = "openai",
    model: str = "gpt-5.4-mini",
) -> QualityReport:
    return summarize_quality_results(evaluate_golden_suite(provider, model))


def _summarize_category(
    category: QualityCategory,
    results: list[QualityResult],
) -> CategoryQualitySummary:
    scoped = [result for result in results if result.category == category]
    passed_cases = sum(1 for result in scoped if result.passed)
    preservation_passed = sum(1 for result in scoped if result.preservation_passed)
    return CategoryQualitySummary(
        category=category,
        total_cases=len(scoped),
        passed_cases=passed_cases,
        preservation_pass_rate=round(preservation_passed / len(scoped), 4) if scoped else 0,
        average_savings_rate=round(mean(result.savings_rate for result in scoped), 4)
        if scoped
        else 0,
        harmful_omission_count=sum(len(result.missing_terms) for result in scoped),
        hallucinated_constraint_count=sum(
            len(result.hallucinated_terms) for result in scoped
        ),
        over_optimization_count=sum(1 for result in scoped if result.over_optimized),
        savings_floor_failures=sum(1 for result in scoped if not result.savings_passed),
    )
