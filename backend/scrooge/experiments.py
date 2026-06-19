from dataclasses import dataclass

from scrooge.optimizer import optimize_prompt
from scrooge.schemas import OptimizeRequest
from scrooge.token_meter import estimate_tokens


@dataclass(frozen=True)
class VariantResult:
    variant: str
    original_tokens: int
    optimized_tokens: int
    saved_tokens: int
    savings_rate: float
    active: bool
    notes: str


def evaluate_variants(request: OptimizeRequest) -> list[VariantResult]:
    original = estimate_tokens(request.prompt, request.provider, request.model)
    balanced = optimize_prompt(request)
    balanced_result = VariantResult(
        variant="rules_balanced",
        original_tokens=balanced.original_tokens.input_tokens,
        optimized_tokens=balanced.optimized_tokens.input_tokens,
        saved_tokens=balanced.saved_tokens,
        savings_rate=balanced.savings_rate,
        active=True,
        notes="Default rule-based optimizer with quality-preserving compression.",
    )
    return [
        VariantResult(
            variant="baseline",
            original_tokens=original.input_tokens,
            optimized_tokens=original.input_tokens,
            saved_tokens=0,
            savings_rate=0,
            active=True,
            notes="Original prompt without Scrooge optimization.",
        ),
        balanced_result,
        VariantResult(
            variant="rules_aggressive",
            original_tokens=balanced_result.original_tokens,
            optimized_tokens=balanced_result.optimized_tokens,
            saved_tokens=balanced_result.saved_tokens,
            savings_rate=balanced_result.savings_rate,
            active=False,
            notes="Planned candidate for stricter compression; disabled until quality gates pass.",
        ),
        VariantResult(
            variant="ml_assisted",
            original_tokens=balanced_result.original_tokens,
            optimized_tokens=balanced_result.optimized_tokens,
            saved_tokens=balanced_result.saved_tokens,
            savings_rate=balanced_result.savings_rate,
            active=False,
            notes="Planned ML candidate generation/evaluation; never auto-applied in v1.",
        ),
    ]
