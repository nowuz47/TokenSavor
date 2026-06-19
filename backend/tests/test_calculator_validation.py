from scrooge.optimizer import optimize_prompt
from scrooge.schemas import OptimizeRequest
from tools.validate_calculator_savings import (
    EXPECTED_OUTPUT_TOKENS,
    MODEL,
    PROVIDER,
    assert_savings_math,
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
