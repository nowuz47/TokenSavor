from scrooge.optimizer import detect_task_type, optimize_prompt
from scrooge.schemas import AttachmentMetadata, AttachmentTokenStatus, OptimizeRequest, TaskType


def test_optimizer_detects_bug_analysis_and_reduces_duplicate_noise() -> None:
    prompt = "\n\n".join(
        [
            "이 코드가 이상한 것 같은데 한번 확인해 주세요",
            "ERROR failed to parse config",
            "ERROR failed to parse config",
        ]
    )

    response = optimize_prompt(OptimizeRequest(prompt=prompt, provider="openai", model="gpt-5.4-mini"))

    assert response.task_type == TaskType.BUG_ANALYSIS
    assert "Root cause" in response.optimized_prompt
    assert response.original_tokens.input_tokens > 0
    assert response.optimized_cost.pricing_version == "openai-2026-06-19"
    assert any(reason.rule_id == "task_template" for reason in response.reasons)


def test_task_detection_supports_log_analysis() -> None:
    assert detect_task_type("CloudWatch log exception traceback") == TaskType.LOG_ANALYSIS


def test_task_detection_supports_korean_enterprise_prompts() -> None:
    data_prompt = (
        "sales_2026_q1.csv를 분석해서 사업부, 지역, 상품군별 매출 증감률을 구하고 "
        "전년 동기 대비 15% 이상 하락한 항목을 찾아주세요."
    )
    calculator_prompt = (
        "계산기 앱을 파이썬으로 만들어주세요. eval()은 쓰지 말고 pytest 테스트도 작성해 주세요."
    )
    bug_prompt = (
        "단축키 Ctrl+Alt+S를 눌러도 대시보드 절감 토큰이 반영되지 않는 버그를 찾아주세요."
    )
    trust_policy_prompt = (
        "한국 대기업 사내 도입을 위한 신뢰 정책을 정리해 주세요. 팀 단위 통계와 원문 프롬프트 저장 금지가 필요합니다."
    )

    assert detect_task_type(data_prompt) == TaskType.DATA_ANALYSIS
    assert detect_task_type(calculator_prompt) == TaskType.GENERAL
    assert detect_task_type(bug_prompt) == TaskType.BUG_ANALYSIS
    assert detect_task_type(trust_policy_prompt) == TaskType.ARCHITECTURE_REVIEW


def test_korean_repeated_logs_are_compressed_and_preserved() -> None:
    prompt = "\n".join(
        ["아래 운영 로그를 분석해서 장애 원인과 즉시 조치 방안을 정리해 주세요."]
        + [
            "2026-06-20 09:01:11 ERROR payment-api timeout order_id=1001 pg=KCP latency=5300ms"
            for _ in range(80)
        ]
        + ["CloudWatch 기준이며 배포 직후 5분 동안만 발생했습니다."]
    )

    response = optimize_prompt(OptimizeRequest(prompt=prompt, provider="openai", model="gpt-5.4-mini"))

    assert response.task_type == TaskType.LOG_ANALYSIS
    assert response.saved_tokens > 0
    assert response.savings_rate >= 0.2
    assert "payment-api" in response.optimized_prompt
    assert "KCP" in response.optimized_prompt


def test_attachment_reference_keeps_total_savings_unknown_without_metadata() -> None:
    response = optimize_prompt(
        OptimizeRequest(
            prompt="Please review the attached file and find the bug.",
            provider="openai",
            model="gpt-5.4-mini",
        )
    )

    assert response.attachment_summary.possible_attachment_reference is True
    assert response.attachment_summary.token_status == AttachmentTokenStatus.UNKNOWN
    assert response.attachment_summary.total_savings_rate is None
    assert response.total_savings_rate is None
    assert response.prompt_savings_rate == response.savings_rate


def test_estimated_attachment_tokens_lower_total_savings_rate() -> None:
    response = optimize_prompt(
        OptimizeRequest(
            prompt="Analyze this uploaded app.log file. ERROR timeout\nERROR timeout\nERROR timeout",
            provider="openai",
            model="gpt-5.4-mini",
            attachments=[
                AttachmentMetadata(
                    name="app.log",
                    mime_type="text/plain",
                    size_bytes=2048,
                    content_hash="sha256:test",
                    token_status=AttachmentTokenStatus.ESTIMATED,
                    estimated_tokens=5000,
                )
            ],
        )
    )

    assert response.attachment_summary.attachment_count == 1
    assert response.attachment_summary.token_status == AttachmentTokenStatus.ESTIMATED
    assert response.attachment_summary.estimated_attachment_tokens == 5000
    assert response.attachment_summary.total_savings_rate is not None
    assert response.attachment_summary.total_savings_rate <= response.prompt_savings_rate


def test_text_attachment_content_is_compressed_and_measured_controlled() -> None:
    log_content = "\n".join(
        ["2026-06-21 09:00:00 ERROR payment-api timeout order_id=1001 latency=5300ms" for _ in range(200)]
        + ['File "/app/payment.py", line 42, in charge']
        + ["TimeoutError: payment gateway timeout"]
    )

    response = optimize_prompt(
        OptimizeRequest(
            prompt="Analyze the attached large-error.log and keep the file, line, and exception.",
            provider="openai",
            model="gpt-5.4-mini",
            attachments=[
                AttachmentMetadata(
                    name="large-error.log",
                    mime_type="text/plain",
                    content=log_content,
                    token_status=AttachmentTokenStatus.UNKNOWN,
                )
            ],
        )
    )

    assert response.attachment_summary.token_status == AttachmentTokenStatus.MEASURED
    assert response.attachment_summary.attachment_original_tokens
    assert response.attachment_summary.attachment_optimized_tokens
    assert response.attachment_summary.attachment_saved_tokens is not None
    assert response.attachment_summary.attachment_savings_rate is not None
    assert response.attachment_summary.attachment_savings_rate >= 0.3
    assert response.attachment_summary.attachment_measurement_source == "measured_controlled"
    assert "large-error.log" in response.optimized_prompt
    assert "TimeoutError" in response.optimized_prompt
    assert response.attachments[0].content is None
    assert response.attachments[0].content_hash is not None
