import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from scrooge.compressor import compress_context
from scrooge.pricing import calculate_cost
from scrooge.schemas import OptimizationReason, OptimizeRequest, OptimizeResponse, TaskType
from scrooge.token_meter import estimate_tokens


TASK_KEYWORDS: list[tuple[TaskType, tuple[str, ...]]] = [
    (
        TaskType.LOG_ANALYSIS,
        (
            "log",
            "logs",
            "stack trace",
            "traceback",
            "exception",
            "cloudwatch",
            "로그",
            "스택트레이스",
            "장애 로그",
            "운영 로그",
        ),
    ),
    (
        TaskType.DATA_ANALYSIS,
        (
            "csv",
            "json",
            "sql",
            "dashboard",
            "metric",
            "metrics",
            "revenue",
            "retention",
            "conversion",
            "latency_ms",
            "분석",
            "데이터",
            "매출",
            "컬럼",
            "지표",
            "집계",
            "이상치",
            "전년",
            "분기",
            "보고용",
        ),
    ),
    (TaskType.CODE_REVIEW, ("review", "code review", "검토", "리뷰")),
    (TaskType.REFACTORING, ("refactor", "리팩터", "리팩토링", "cleanup", "정리")),
    (TaskType.ARCHITECTURE_REVIEW, ("architecture", "설계", "아키텍처")),
    (
        TaskType.BUG_ANALYSIS,
        ("bug", "error", "fix", "failed", "failure", "오류", "에러", "이상", "버그", "고쳐", "수정"),
    ),
    (TaskType.TEST_GENERATION, ("test", "pytest", "jest", "테스트", "테스트 작성", "테스트 케이스")),
]

IMPLEMENTATION_KEYWORDS = (
    "build",
    "create",
    "implement",
    "add",
    "make",
    "만들",
    "구현",
    "작성",
    "추가",
)

CODE_ARTIFACT_KEYWORDS = (
    "app",
    "api",
    "ui",
    "python",
    "javascript",
    "typescript",
    "react",
    "tauri",
    "fastapi",
    "앱",
    "계산기",
    "파이썬",
    "프론트엔드",
    "백엔드",
)

TEMPLATES: dict[TaskType, str] = {
    TaskType.BUG_ANALYSIS: (
        "Goal: Identify the likely bug cause and propose a minimal fix.\n"
        "Return:\n1. Root cause\n2. Fix plan\n3. Impact/risk\n4. Tests to run"
    ),
    TaskType.CODE_REVIEW: (
        "Goal: Review for correctness, regressions, security, and missing tests.\n"
        "Return findings first, ordered by severity, with file/line references when available."
    ),
    TaskType.REFACTORING: (
        "Goal: Refactor while preserving behavior.\n"
        "Return: approach, scoped changes, compatibility risks, and tests."
    ),
    TaskType.TEST_GENERATION: (
        "Goal: Add focused tests for the described behavior.\n"
        "Return: test cases, fixtures/mocks, and edge cases."
    ),
    TaskType.ARCHITECTURE_REVIEW: (
        "Goal: Evaluate architecture tradeoffs and implementation risks.\n"
        "Return: recommendation, alternatives, risks, and rollout notes."
    ),
    TaskType.LOG_ANALYSIS: (
        "Goal: Analyze logs and isolate the most likely failure pattern.\n"
        "Return: top signals, suspected cause, next checks, and remediation."
    ),
    TaskType.DATA_ANALYSIS: (
        "Goal: Analyze the provided data request while preserving columns, filters, metrics, and time ranges.\n"
        "Return: summary, method/query, notable findings, caveats, and validation checks."
    ),
    TaskType.GENERAL: (
        "Goal: Complete the user request efficiently.\n"
        "Return concise, actionable output with assumptions called out."
    ),
}


@dataclass(frozen=True)
class OptimizedDraft:
    task_type: TaskType
    prompt: str
    reasons: list[OptimizationReason]


def detect_task_type(prompt: str) -> TaskType:
    lowered = prompt.lower()
    if _looks_like_implementation_request(lowered):
        return TaskType.GENERAL
    if _has_explicit_bug_intent(lowered) and not _has_log_analysis_context(prompt):
        return TaskType.BUG_ANALYSIS
    if _has_trust_policy_context(lowered):
        return TaskType.ARCHITECTURE_REVIEW
    for task_type, keywords in TASK_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return task_type
    return TaskType.GENERAL


def _looks_like_implementation_request(lowered_prompt: str) -> bool:
    has_implementation_intent = any(keyword in lowered_prompt for keyword in IMPLEMENTATION_KEYWORDS)
    has_code_artifact = any(keyword in lowered_prompt for keyword in CODE_ARTIFACT_KEYWORDS)
    has_review_or_debug_intent = any(
        keyword in lowered_prompt
        for keyword in (
            "review",
            "code review",
            "검토",
            "리뷰",
            "bug",
            "error",
            "failed",
            "failure",
            "오류",
            "에러",
            "버그",
            "장애",
        )
    )
    return has_implementation_intent and has_code_artifact and not has_review_or_debug_intent


def _has_explicit_bug_intent(lowered_prompt: str) -> bool:
    return any(
        keyword in lowered_prompt
        for keyword in ("bug", "버그", "오류", "에러", "고쳐", "수정", "반영되지", "안됩니다", "않습니다")
    )


def _has_log_analysis_context(prompt: str) -> bool:
    lowered = prompt.lower()
    if any(keyword in lowered for keyword in ("cloudwatch", "운영 로그", "장애 로그", "로그 분석")):
        return True
    error_like_lines = sum(
        1
        for line in prompt.splitlines()
        if re.search(r"\b(error|exception|traceback|fatal|warn)\b", line, re.IGNORECASE)
    )
    return error_like_lines >= 2


def _has_trust_policy_context(lowered_prompt: str) -> bool:
    policy_terms = (
        "trust policy",
        "governance",
        "compliance",
        "privacy",
        "raw prompt",
        "prompt hash",
        "local storage",
        "team-level metrics",
        "신뢰 정책",
        "거버넌스",
        "컴플라이언스",
        "개인정보",
        "원문 프롬프트",
        "팀 단위",
        "로컬 저장",
    )
    return any(term in lowered_prompt for term in policy_terms)


def optimize_prompt(request: OptimizeRequest) -> OptimizeResponse:
    draft = build_optimized_draft(request.prompt, request.task_type)
    original_tokens = estimate_tokens(request.prompt, request.provider, request.model)
    optimized_tokens = estimate_tokens(draft.prompt, request.provider, request.model)
    original_cost = calculate_cost(
        original_tokens, request.provider, request.model, request.expected_output_tokens
    )
    optimized_cost = calculate_cost(
        optimized_tokens, request.provider, request.model, request.expected_output_tokens
    )
    saved_tokens = max(0, original_tokens.input_tokens - optimized_tokens.input_tokens)
    saved_cost = max(0.0, original_cost.total_cost_usd - optimized_cost.total_cost_usd)
    savings_rate = saved_tokens / original_tokens.input_tokens if original_tokens.input_tokens else 0

    return OptimizeResponse(
        request_id=str(uuid4()),
        task_type=draft.task_type,
        original_prompt=request.prompt,
        optimized_prompt=draft.prompt,
        original_tokens=original_tokens,
        optimized_tokens=optimized_tokens,
        original_cost=original_cost,
        optimized_cost=optimized_cost,
        saved_tokens=saved_tokens,
        saved_cost_usd=round(saved_cost, 8),
        savings_rate=round(savings_rate, 4),
        reasons=draft.reasons,
        created_at=datetime.now(timezone.utc),
    )


def build_optimized_draft(prompt: str, task_type: TaskType | None = None) -> OptimizedDraft:
    resolved_task = task_type or detect_task_type(prompt)
    cleaned, cleanup_rules = _normalize_prompt(prompt)
    compressed = compress_context(cleaned)

    reasons = [
        OptimizationReason(
            rule_id="task_template",
            description=f"Applied {resolved_task.value} response structure.",
        )
    ]
    reasons.extend(
        OptimizationReason(rule_id=rule, description=_describe_rule(rule))
        for rule in cleanup_rules + compressed.rules
    )

    optimized = (
        f"{TEMPLATES[resolved_task]}\n\n"
        "Constraints:\n"
        "- Preserve explicit user requirements.\n"
        "- Ask only if required information is missing.\n"
        "- Keep the response proportional to the task.\n\n"
        f"User request/context:\n{compressed.text.strip()}"
    )
    return OptimizedDraft(task_type=resolved_task, prompt=optimized.strip(), reasons=reasons)


def _normalize_prompt(prompt: str) -> tuple[str, list[str]]:
    rules: list[str] = []
    text = prompt.strip()
    collapsed = re.sub(r"\n{3,}", "\n\n", text)
    if collapsed != text:
        rules.append("collapse_blank_lines")
    text = collapsed

    lines = text.splitlines()
    deduped: list[str] = []
    previous = None
    for line in lines:
        if line == previous and line.strip():
            if "dedupe_adjacent_lines" not in rules:
                rules.append("dedupe_adjacent_lines")
            continue
        deduped.append(line)
        previous = line
    text = "\n".join(deduped)
    return text, rules


def _describe_rule(rule_id: str) -> str:
    descriptions = {
        "collapse_blank_lines": "Collapsed repeated blank lines.",
        "dedupe_adjacent_lines": "Removed adjacent duplicate lines.",
        "generic_head_tail_compaction": "Compacted long context using head and tail samples.",
        "log_error_frequency_summary": "Summarized repeated log errors by frequency.",
        "log_representative_samples": "Kept representative error samples.",
        "stacktrace_cause_preservation": "Preserved stack trace causes and exception lines.",
        "stacktrace_frame_limit": "Limited repeated stack frames.",
        "diff_header_preservation": "Preserved diff file and hunk headers.",
        "diff_changed_line_sampling": "Sampled changed diff lines.",
        "command_output_test_summary": "Summarized test runner output by failure signals.",
        "command_output_failure_preservation": "Preserved failing tests, assertion lines, and file references.",
        "command_output_git_status_summary": "Summarized git status output by branch and change counts.",
        "command_output_changed_file_sampling": "Kept representative changed file samples.",
        "command_output_search_summary": "Summarized search output by matched files and total hits.",
        "command_output_match_sampling": "Kept representative search matches.",
        "protected_block_preservation": "Kept user-marked protected context verbatim.",
    }
    return descriptions.get(rule_id, rule_id.replace("_", " ").capitalize())
