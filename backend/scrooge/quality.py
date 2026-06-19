from dataclasses import dataclass

from scrooge.optimizer import optimize_prompt
from scrooge.schemas import OptimizeRequest, OptimizeResponse, TaskType


@dataclass(frozen=True)
class GoldenPrompt:
    name: str
    prompt: str
    task_type: TaskType
    required_terms: tuple[str, ...]


@dataclass(frozen=True)
class QualityResult:
    name: str
    passed: bool
    savings_rate: float
    missing_terms: tuple[str, ...]
    optimized_tokens: int
    original_tokens: int


GOLDEN_PROMPTS: tuple[GoldenPrompt, ...] = (
    GoldenPrompt(
        name="calculator_app_generation",
        task_type=TaskType.GENERAL,
        required_terms=("HTML", "CSS", "JavaScript", "tests", "divide by zero"),
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
        name="bug_analysis",
        task_type=TaskType.BUG_ANALYSIS,
        required_terms=("ParserError", "config.py", "line 45"),
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
        name="git_diff_review",
        task_type=TaskType.CODE_REVIEW,
        required_terms=("diff --git", "@@", "auth.py"),
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
        name="log_analysis",
        task_type=TaskType.LOG_ANALYSIS,
        required_terms=("payment-service", "timeout", "Traceback"),
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
        name="long_log_analysis",
        task_type=TaskType.LOG_ANALYSIS,
        required_terms=("payment-service", "timeout", "upstream timeout"),
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
        name="long_diff_review",
        task_type=TaskType.CODE_REVIEW,
        required_terms=("diff --git", "@@", "auth.py"),
        prompt="\n".join(
            [
                "Review this diff for security regressions.",
                "diff --git a/auth.py b/auth.py",
                "@@ -10,7 +10,7 @@",
            ]
            + ["- return user.is_admin", "+ return True"] * 70
        ),
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
    return evaluate_response(golden.name, golden.required_terms, response)


def evaluate_response(
    name: str,
    required_terms: tuple[str, ...],
    response: OptimizeResponse,
) -> QualityResult:
    optimized = response.optimized_prompt.lower()
    missing_terms = tuple(term for term in required_terms if term.lower() not in optimized)
    return QualityResult(
        name=name,
        passed=not missing_terms,
        savings_rate=response.savings_rate,
        missing_terms=missing_terms,
        original_tokens=response.original_tokens.input_tokens,
        optimized_tokens=response.optimized_tokens.input_tokens,
    )


def evaluate_golden_suite(
    provider: str = "openai",
    model: str = "gpt-5.4-mini",
) -> list[QualityResult]:
    return [evaluate_golden_prompt(item, provider, model) for item in GOLDEN_PROMPTS]
