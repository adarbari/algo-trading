"""Registry of feature definitions known to the pipeline."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from algotrade.features import option_liquidity


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    version: int
    inputs: tuple[str, ...]
    description: str
    # Output columns and their types ("str" | "float" | "int" | "bool" | "date"). Selections
    # may reference them as ``rollup.<name>@v<version>.<column>``.
    columns: Mapping[str, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.name}@v{self.version}"

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
            option_liquidity.COLUMNS,
        ),
    )
}
