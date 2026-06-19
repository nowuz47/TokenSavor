import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from scrooge.schemas import CostBreakdown, TokenBreakdown


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    input_per_million_usd: float
    output_per_million_usd: float
    cached_input_per_million_usd: float | None
    version: str
    source_url: str
    effective_date: str


class PricingRegistry:
    def __init__(self, prices: list[ModelPrice]) -> None:
        self._prices = {(p.provider.lower(), p.model.lower()): p for p in prices}

    @classmethod
    def from_file(cls, path: Path) -> "PricingRegistry":
        raw = json.loads(path.read_text(encoding="utf-8"))
        prices = [
            ModelPrice(
                provider=item["provider"],
                model=item["model"],
                input_per_million_usd=float(item["input_per_million_usd"]),
                output_per_million_usd=float(item["output_per_million_usd"]),
                cached_input_per_million_usd=(
                    float(item["cached_input_per_million_usd"])
                    if item.get("cached_input_per_million_usd") is not None
                    else None
                ),
                version=item["version"],
                source_url=item["source_url"],
                effective_date=item["effective_date"],
            )
            for item in raw["models"]
        ]
        return cls(prices)

    def get(self, provider: str, model: str) -> ModelPrice:
        key = (provider.lower(), model.lower())
        if key in self._prices:
            return self._prices[key]

        provider_matches = [p for (p_provider, _), p in self._prices.items() if p_provider == key[0]]
        if provider_matches:
            return provider_matches[0]

        return next(iter(self._prices.values()))

    def list_models(self) -> list[ModelPrice]:
        return sorted(self._prices.values(), key=lambda p: (p.provider, p.model))


def calculate_cost(
    tokens: TokenBreakdown,
    provider: str,
    model: str,
    expected_output_tokens: int = 0,
) -> CostBreakdown:
    price = get_pricing_registry().get(provider, model)
    input_cost = tokens.input_tokens * price.input_per_million_usd / 1_000_000
    output_cost = expected_output_tokens * price.output_per_million_usd / 1_000_000
    return CostBreakdown(
        input_cost_usd=round(input_cost, 8),
        output_cost_usd=round(output_cost, 8),
        total_cost_usd=round(input_cost + output_cost, 8),
        pricing_version=price.version,
        source_url=price.source_url,
        is_estimate=tokens.is_estimate,
    )


@lru_cache
def get_pricing_registry() -> PricingRegistry:
    path = Path(__file__).parent / "fixtures" / "pricing_versions.json"
    return PricingRegistry.from_file(path)

