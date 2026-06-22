import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from scrooge.attachment_optimizer import optimize_text_attachments
from scrooge.compressor import compress_context
from scrooge.pricing import calculate_cost
from scrooge.schemas import (
    AttachmentMetadata,
    AttachmentSummary,
    AttachmentTokenStatus,
    OptimizationMode,
    OptimizationReason,
    OptimizeRequest,
    OptimizeResponse,
    TaskType,
)
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
    optimization_mode: OptimizationMode = OptimizationMode.TOKEN_SAVINGS
    estimated_work_savings_minutes: int = 0
    estimated_followup_reduction: float = 0
    work_optimization_reason: str | None = None


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
    attachment_optimization = optimize_text_attachments(request.attachments, request.provider, request.model)
    draft = build_optimized_draft(request.prompt, request.task_type)
    prompt_original_tokens = estimate_tokens(request.prompt, request.provider, request.model)
    prompt_optimized_tokens = estimate_tokens(draft.prompt, request.provider, request.model)
    optimized_prompt = draft.prompt
    if attachment_optimization.context_text:
        optimized_prompt = f"{draft.prompt}\n\n{attachment_optimization.context_text}".strip()

    attachment_original_tokens = sum(item.original_tokens or 0 for item in attachment_optimization.attachments)
    original_token_count = prompt_original_tokens.input_tokens + attachment_original_tokens
    original_tokens = prompt_original_tokens.model_copy(update={"input_tokens": original_token_count})
    optimized_tokens = estimate_tokens(optimized_prompt, request.provider, request.model)
    original_cost = calculate_cost(
        original_tokens, request.provider, request.model, request.expected_output_tokens
    )
    optimized_cost = calculate_cost(
        optimized_tokens, request.provider, request.model, request.expected_output_tokens
    )
    saved_tokens = max(0, original_tokens.input_tokens - optimized_tokens.input_tokens)
    saved_cost = max(0.0, original_cost.total_cost_usd - optimized_cost.total_cost_usd)
    savings_rate = saved_tokens / original_tokens.input_tokens if original_tokens.input_tokens else 0
    prompt_saved_tokens = max(0, prompt_original_tokens.input_tokens - prompt_optimized_tokens.input_tokens)
    prompt_savings_rate = (
        prompt_saved_tokens / prompt_original_tokens.input_tokens if prompt_original_tokens.input_tokens else 0
    )
    attachment_summary = build_attachment_summary(
        prompt=request.prompt,
        attachments=attachment_optimization.attachments,
        original_input_tokens=prompt_original_tokens.input_tokens,
        optimized_input_tokens=optimized_tokens.input_tokens,
        saved_tokens=prompt_saved_tokens,
        prompt_savings_rate=prompt_savings_rate,
    )

    return OptimizeResponse(
        request_id=str(uuid4()),
        task_type=draft.task_type,
        original_prompt=request.prompt,
        optimized_prompt=optimized_prompt,
        original_tokens=original_tokens,
        optimized_tokens=optimized_tokens,
        original_cost=original_cost,
        optimized_cost=optimized_cost,
        saved_tokens=saved_tokens,
        saved_cost_usd=round(saved_cost, 8),
        savings_rate=round(savings_rate, 4),
        prompt_savings_rate=round(prompt_savings_rate, 4),
        total_savings_rate=attachment_summary.total_savings_rate,
        attachment_summary=attachment_summary,
        attachments=attachment_optimization.attachments,
        optimization_mode=draft.optimization_mode,
        estimated_work_savings_minutes=draft.estimated_work_savings_minutes,
        estimated_followup_reduction=draft.estimated_followup_reduction,
        work_optimization_reason=draft.work_optimization_reason,
        reasons=draft.reasons + attachment_optimization.reasons,
        created_at=datetime.now(timezone.utc),
    )


def build_attachment_summary(
    prompt: str,
    attachments: list[AttachmentMetadata],
    original_input_tokens: int,
    optimized_input_tokens: int,
    saved_tokens: int,
    prompt_savings_rate: float,
) -> AttachmentSummary:
    possible_reference = detect_possible_attachment_reference(prompt)
    if not attachments:
        if possible_reference:
            return AttachmentSummary(
                attachment_count=0,
                token_status=AttachmentTokenStatus.UNKNOWN,
                possible_attachment_reference=True,
                prompt_original_tokens=original_input_tokens,
                prompt_optimized_tokens=optimized_input_tokens,
                prompt_saved_tokens=saved_tokens,
                prompt_savings_rate=round(prompt_savings_rate, 4),
                note="Possible attachment reference detected; attachment tokens are not included.",
            )
        return AttachmentSummary(
            attachment_count=0,
            token_status=AttachmentTokenStatus.NOT_PRESENT,
            possible_attachment_reference=False,
            prompt_original_tokens=original_input_tokens,
            prompt_optimized_tokens=optimized_input_tokens,
            prompt_saved_tokens=saved_tokens,
            total_original_tokens=original_input_tokens,
            total_optimized_tokens=optimized_input_tokens,
            total_saved_tokens=saved_tokens,
            prompt_savings_rate=round(prompt_savings_rate, 4),
            total_savings_rate=round(prompt_savings_rate, 4),
            note="No attachment metadata was provided.",
        )

    known_estimated = [
        int(item.estimated_tokens)
        for item in attachments
        if item.estimated_tokens is not None and item.token_status in {AttachmentTokenStatus.ESTIMATED, AttachmentTokenStatus.MEASURED}
    ]
    known_measured = [
        int(item.measured_tokens)
        for item in attachments
        if item.measured_tokens is not None and item.token_status == AttachmentTokenStatus.MEASURED
    ]
    has_unknown = any(
        item.token_status == AttachmentTokenStatus.UNKNOWN
        or (item.token_status == AttachmentTokenStatus.ESTIMATED and item.estimated_tokens is None)
        or (item.token_status == AttachmentTokenStatus.MEASURED and item.measured_tokens is None and item.estimated_tokens is None)
        for item in attachments
    )
    all_measured = bool(attachments) and all(
        item.token_status == AttachmentTokenStatus.MEASURED and item.measured_tokens is not None
        for item in attachments
    )
    estimated_attachment_tokens = sum(known_estimated) if known_estimated else None
    measured_attachment_tokens = sum(known_measured) if known_measured else None
    controlled_original = [
        int(item.original_tokens)
        for item in attachments
        if item.original_tokens is not None and item.token_status == AttachmentTokenStatus.MEASURED
    ]
    controlled_optimized = [
        int(item.optimized_tokens)
        for item in attachments
        if item.optimized_tokens is not None and item.token_status == AttachmentTokenStatus.MEASURED
    ]
    controlled_sources = {
        item.measurement_source
        for item in attachments
        if item.measurement_source and item.token_status == AttachmentTokenStatus.MEASURED
    }
    if controlled_original and len(controlled_original) == len(attachments) and len(controlled_optimized) == len(attachments):
        attachment_original = sum(controlled_original)
        attachment_optimized = sum(controlled_optimized)
        attachment_saved = max(0, attachment_original - attachment_optimized)
        total_original = original_input_tokens + attachment_original
        total_optimized = optimized_input_tokens
        total_saved = max(0, total_original - total_optimized)
        return AttachmentSummary(
            attachment_count=len(attachments),
            token_status=AttachmentTokenStatus.MEASURED,
            possible_attachment_reference=possible_reference,
            prompt_original_tokens=original_input_tokens,
            prompt_optimized_tokens=max(0, optimized_input_tokens - attachment_optimized),
            prompt_saved_tokens=saved_tokens,
            estimated_attachment_tokens=attachment_original,
            measured_attachment_tokens=attachment_optimized,
            attachment_original_tokens=attachment_original,
            attachment_optimized_tokens=attachment_optimized,
            attachment_saved_tokens=attachment_saved,
            attachment_savings_rate=round(attachment_saved / attachment_original, 4) if attachment_original else 0,
            attachment_measurement_source=",".join(sorted(controlled_sources)) or "measured_controlled",
            total_original_tokens=total_original,
            total_optimized_tokens=total_optimized,
            total_saved_tokens=total_saved,
            prompt_savings_rate=round(prompt_savings_rate, 4),
            total_savings_rate=round(total_saved / total_original, 4) if total_original else 0,
            note="Text attachment savings use controlled local measurement.",
        )

    attachment_tokens_for_total = measured_attachment_tokens if all_measured else estimated_attachment_tokens

    if has_unknown or attachment_tokens_for_total is None:
        status = AttachmentTokenStatus.UNKNOWN
        total_original = None
        total_optimized = None
        total_savings_rate = None
        total_saved = None
        note = "Attachment metadata was present, but attachment tokens are not fully measured or estimated."
    else:
        status = AttachmentTokenStatus.MEASURED if all_measured else AttachmentTokenStatus.ESTIMATED
        total_original = original_input_tokens + attachment_tokens_for_total
        total_optimized = optimized_input_tokens + attachment_tokens_for_total
        total_saved = max(0, total_original - total_optimized)
        total_savings_rate = round(total_saved / total_original, 4) if total_original else 0
        note = (
            "Attachment-inclusive savings use measured attachment tokens."
            if status == AttachmentTokenStatus.MEASURED
            else "Attachment-inclusive savings use estimated attachment tokens."
        )

    return AttachmentSummary(
        attachment_count=len(attachments),
        token_status=status,
        possible_attachment_reference=possible_reference,
        prompt_original_tokens=original_input_tokens,
        prompt_optimized_tokens=optimized_input_tokens,
        prompt_saved_tokens=saved_tokens,
        estimated_attachment_tokens=estimated_attachment_tokens,
        measured_attachment_tokens=measured_attachment_tokens,
        attachment_original_tokens=estimated_attachment_tokens or measured_attachment_tokens,
        attachment_optimized_tokens=attachment_tokens_for_total,
        attachment_saved_tokens=0 if attachment_tokens_for_total is not None else None,
        attachment_savings_rate=0 if attachment_tokens_for_total is not None else None,
        attachment_measurement_source="measured_provider" if all_measured else None,
        total_original_tokens=total_original,
        total_optimized_tokens=total_optimized,
        total_saved_tokens=total_saved,
        prompt_savings_rate=round(prompt_savings_rate, 4),
        total_savings_rate=total_savings_rate,
        note=note,
    )


def detect_possible_attachment_reference(prompt: str) -> bool:
    lowered = prompt.lower()
    attachment_terms = (
        "attachment",
        "attached",
        "uploaded",
        "upload",
        "file",
        "files",
        "첨부",
        "첨부한",
        "첨부된",
        "파일",
        "파일을 보고",
        "업로드",
    )
    return any(term in lowered for term in attachment_terms)


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

    if _looks_like_broad_task_request(cleaned):
        reason = _task_optimization_reason(cleaned)
        reasons.append(
            OptimizationReason(
                rule_id="task_optimization_template",
                description=reason,
            )
        )
        return OptimizedDraft(
            task_type=resolved_task,
            prompt=_build_task_optimization_prompt(cleaned, resolved_task),
            reasons=reasons,
            optimization_mode=OptimizationMode.TASK_OPTIMIZATION,
            estimated_work_savings_minutes=_estimate_work_savings_minutes(cleaned, resolved_task),
            estimated_followup_reduction=0.25,
            work_optimization_reason=reason,
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


def _looks_like_broad_task_request(prompt: str) -> bool:
    stripped = prompt.strip()
    if not stripped or len(stripped) > 240 or len(stripped.splitlines()) > 4:
        return False
    lowered = stripped.lower()
    english_broad_terms = (
        "all",
        "entire",
        "whole",
        "project",
        "repo",
        "repository",
        "workspace",
        "codebase",
        "logs",
        "log files",
        "files",
        "attached files",
    )
    korean_broad_terms = (
        "모두",
        "전체",
        "전부",
        "프로젝트",
        "저장소",
        "워크스페이스",
        "코드베이스",
        "로그파일",
        "로그 파일",
        "파일들",
        "첨부파일",
        "첨부 파일",
    )
    english_action_terms = (
        "read",
        "scan",
        "find",
        "analyze",
        "review",
        "summarize",
        "debug",
    )
    korean_action_terms = (
        "읽",
        "찾",
        "분석",
        "검토",
        "정리",
        "확인",
        "디버그",
    )
    scope_like = _contains_english_term(lowered, english_broad_terms) or any(
        term in lowered for term in korean_broad_terms
    )
    action_like = _contains_english_term(lowered, english_action_terms) or any(
        term in lowered for term in korean_action_terms
    )
    return scope_like and action_like


def _contains_english_term(lowered_prompt: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", lowered_prompt) for term in terms)


def _contains_hangul(prompt: str) -> bool:
    return bool(re.search(r"[가-힣]", prompt))


def _task_optimization_reason(prompt: str) -> str:
    if _contains_hangul(prompt):
        return "짧지만 프로젝트/파일 범위가 넓은 요청이라 작업 최적화 템플릿을 적용했습니다."
    return "Applied task optimization because the prompt is short but asks for broad project/file scope."


def _estimate_work_savings_minutes(prompt: str, task_type: TaskType) -> int:
    lowered = prompt.lower()
    minutes = 6
    if any(term in lowered for term in ("project", "repo", "repository", "workspace", "프로젝트", "저장소", "워크스페이스")):
        minutes += 4
    if any(term in lowered for term in ("logs", "log files", "로그파일", "로그 파일")):
        minutes += 4
    if any(term in lowered for term in ("all", "entire", "whole", "모두", "전체", "전부")):
        minutes += 3
    if task_type in {TaskType.LOG_ANALYSIS, TaskType.DATA_ANALYSIS, TaskType.BUG_ANALYSIS}:
        minutes += 2
    return min(minutes, 18)


def _build_task_optimization_prompt(prompt: str, task_type: TaskType) -> str:
    if _contains_hangul(prompt):
        return (
            "작업 최적화 요청:\n"
            "목표:\n"
            f"- {prompt.strip()}\n\n"
            "작업 범위:\n"
            "- 현재 프로젝트, 첨부, 작업공간에서 관련 파일과 로그를 먼저 찾습니다.\n"
            "- 확인한 파일명, 경로, 명령, 근거를 결과에 남깁니다.\n"
            "- 반복 로그는 빈도별로 묶고 대표 에러와 예외 원인을 보존합니다.\n\n"
            "출력 형식:\n"
            "1. 확인한 범위\n"
            "2. 핵심 신호(top signals)와 빈도\n"
            "3. 원인 후보(suspected cause)와 권장안(recommendation)\n"
            "4. 대안(alternatives), 위험(risks), 추가로 확인할 파일/명령\n"
            "5. 바로 실행할 다음 조치\n\n"
            "제약:\n"
            "- 실제로 확인하지 않은 파일 내용은 추정하지 않습니다.\n"
            "- 접근할 수 없는 파일이나 누락된 권한은 명확히 표시합니다.\n"
            "- 사용자 목표를 줄이지 말고, 불필요한 재질문을 줄이는 방향으로 진행합니다."
        )
    return (
        "Task optimization request:\n"
        "Goal:\n"
        f"- {prompt.strip()}\n\n"
        "Scope:\n"
        "- First discover relevant files, logs, and workspace context.\n"
        "- Report the file paths, commands, and evidence that were actually checked.\n"
        "- Group repeated log lines by frequency while preserving representative errors and exception causes.\n\n"
        "Return format:\n"
        "1. Checked scope\n"
        "2. Top signals and frequency\n"
        "3. Suspected cause and recommendation\n"
        "4. Alternatives, risks, and files/commands to verify next\n"
        "5. Immediate next actions\n\n"
        "Constraints:\n"
        "- Do not infer contents of files that were not inspected.\n"
        "- Call out missing access or unavailable files explicitly.\n"
        "- Preserve the user's goal and reduce avoidable follow-up questions."
    )


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
