"""Registry of feature definitions known to the pipeline."""

from dataclasses import dataclass

from algotrade.features import option_liquidity


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    version: int
    inputs: tuple[str, ...]
    description: str

    @property
    def table(self) -> str:
        return f"rollups/instrument/{self.name}@v{self.version}"


FEATURES: dict[str, FeatureSpec] = {
    spec.table: spec
    for spec in (
        FeatureSpec(
            option_liquidity.NAME,
            option_liquidity.VERSION,
            ("chains/option_quotes", "chains/underlying_quotes", "chains/status"),
            "Short-premium tradeability tiers (A-D) for puts and calls at the target expiry",
        ),
    )
}
