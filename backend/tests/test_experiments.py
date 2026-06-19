from scrooge.experiments import evaluate_variants
from scrooge.schemas import OptimizeRequest


def test_ab_variants_keep_balanced_rules_as_default() -> None:
    variants = evaluate_variants(
        OptimizeRequest(
            prompt="ERROR timeout\nERROR timeout\nERROR timeout",
            provider="openai",
            model="gpt-5.4-mini",
        )
    )

    by_name = {variant.variant: variant for variant in variants}
    assert by_name["baseline"].active
    assert by_name["rules_balanced"].active
    assert not by_name["rules_aggressive"].active
    assert not by_name["ml_assisted"].active
