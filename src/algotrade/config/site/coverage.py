"""Coverage thresholds of the nightly (``sources.toml [quality.coverage.<group>.<column>]``,
ADR 0043): for each key feature, the least share of the instruments it applies to that must
have a value, per tier, and the largest day-over-day drop, with the severity of a breach. Split from
``settings.py`` (re-exported there) to keep that file under the length limit."""

from dataclasses import dataclass

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

LEVELS = ("WARN", "FAIL")
# a non-null value; a stored row (a null date is not a gap); "recent": a date at most
# max_age_days before the session, or a value in or_value (overdue earnings)
COVERED_BY = ("value", "row", "recent")
KEYS = (
    "core_min", "rest_min", "max_drop", "level", "core_level", "covered_by", "max_age_days",
    "or_value",
)  # fmt: skip


@dataclass(frozen=True)
class CoverageRule:
    """One feature (``<group>.<column>``, e.g. ``iv30.iv30``) and its limits. ``core_min`` /
    ``rest_min``: the least covered share of the applicable names of that tier; ``max_drop``:
    the largest fall in a tier's share against the previous session; ``level`` (and
    ``core_level`` for the core tier) is what a breach is: WARN is reported, FAIL fails the
    step. ``covered_by`` row: the instrument having a row in the group's table counts; recent: of
    the names with a row, those whose date is at most ``max_age_days`` before the session or
    whose ``or_value`` column has a value (a company long past its last report with no next date
    is overdue: the calendar source dropped it)."""

    feature: str
    core_min: float = 0.95
    rest_min: float = 0.80
    max_drop: float = 0.05
    level: str = "WARN"
    core_level: str = ""  # "": the same as ``level``
    covered_by: str = "value"
    max_age_days: int = 100
    or_value: str = ""  # "recent": a sibling column whose value also covers

    def level_of(self, tier: str) -> str:
        return (self.core_level or self.level) if tier == "core" else self.level


def load_coverage(quality: Table, defaults: tuple[CoverageRule, ...]) -> tuple[CoverageRule, ...]:
    """``[quality.coverage.*]`` over ``defaults``: a feature named in the file replaces its
    default rule (its unset keys keep the default's); a feature the file alone names starts
    from the generic limits."""
    section = quality.raw("coverage")
    if section is None:
        return defaults
    root = quality.table("coverage", list(section) if isinstance(section, dict) else [])
    rules = {r.feature: r for r in defaults}
    for group in root.names():
        group_table = root.table(group, list(root.raw(group) or []))
        for column in group_table.names():
            feature = f"{group}.{column}"
            t = group_table.table(column, KEYS)
            base = rules.get(feature, CoverageRule(feature))
            level = t.choice("level", base.level, LEVELS)
            core_level = t.choice("core_level", base.core_level or level, LEVELS)
            rules[feature] = CoverageRule(
                feature,
                core_min=t.fraction("core_min", base.core_min),
                rest_min=t.fraction("rest_min", base.rest_min),
                max_drop=t.fraction("max_drop", base.max_drop),
                level=level,
                core_level=core_level,
                covered_by=t.choice("covered_by", base.covered_by, COVERED_BY),
                max_age_days=t.integer("max_age_days", base.max_age_days, minimum=1),
                or_value=t.text("or_value", base.or_value),
            )
    unknown = [f for f in rules if f.count(".") != 1]
    if unknown:
        raise ConfigurationError(f"{quality.where} coverage: {unknown} must be <group>.<column>")
    return tuple(rules.values())


# Used when sources.toml has no [quality.coverage] section: the key features of a night; mins sit
# a little under the session 2026-10-02 coverage (core 98-100%, rest 79-99%); every core name
# has an earnings row; no core company is overdue (last report over 100 days ago, no next date:
# FDX on 2026-10-02, dropped from the Nasdaq calendar).
DEFAULT_COVERAGE = (
    CoverageRule("price_stats.close", core_min=0.99, rest_min=0.95, core_level="FAIL"),
    CoverageRule("price_stats.high_52w", core_min=0.95, rest_min=0.70),
    CoverageRule("iv30.iv30", core_min=0.99, rest_min=0.75),
    CoverageRule("earnings.next_earnings_date", core_min=1.0, rest_min=0.75, covered_by="row"),
    CoverageRule(
        "earnings.last_earnings_date",
        core_min=1.0,
        rest_min=0.0,
        max_drop=1.0,
        covered_by="recent",
        or_value="next_earnings_date",
    ),
)
