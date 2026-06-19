from scrooge.optimizer import optimize_prompt
from scrooge.schemas import OptimizeRequest
from tools.validate_calculator_savings import (
    CALCULATOR_PROMPTS,
    EXPECTED_OUTPUT_TOKENS,
    MODEL,
    PROVIDER,
    assert_savings_math,
    task_type_for_case,
)


def test_calculator_savings_math_is_independently_verifiable() -> None:
    response = optimize_prompt(
        OptimizeRequest(
            prompt=(
                "Codex에게 요청: 파이썬 계산기를 만들어주세요.\n"
                "요구사항: 사칙연산, 괄호, 음수 지원.\n"
                "요구사항: 사칙연산, 괄호, 음수 지원.\n"
                "ERROR unsupported operator\n"
                "ERROR unsupported operator"
            ),
            provider=PROVIDER,
            model=MODEL,
            task_type="bug_analysis",
            expected_output_tokens=EXPECTED_OUTPUT_TOKENS,
        )
    )

    assert_savings_math(response.model_dump(mode="json"))


def test_realistic_codex_calculator_app_prompt_is_verifiable() -> None:
    case_name = "codex_calculator_app_request"
    response = optimize_prompt(
        OptimizeRequest(
            prompt=CALCULATOR_PROMPTS[case_name],
            provider=PROVIDER,
            model=MODEL,
            task_type=task_type_for_case(case_name),
            expected_output_tokens=EXPECTED_OUTPUT_TOKENS,
        )
    )

    assert response.original_tokens.input_tokens > response.optimized_tokens.input_tokens
    assert_savings_math(response.model_dump(mode="json"))
