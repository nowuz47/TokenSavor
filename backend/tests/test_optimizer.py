from scrooge.optimizer import detect_task_type, optimize_prompt
from scrooge.schemas import OptimizeRequest, TaskType


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

