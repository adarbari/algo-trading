"""Coverage acceptance (ADR 0043): per key feature and tier, the share of the instruments the
feature APPLIES to that have a value for the session, graded against ``sources.toml
[quality.coverage.*]`` (a minimum per tier and a largest day-over-day drop), so a silent gap
(515 optionable names with no ``iv30``; two S&P 500 members with no earnings row) fails or
warns instead of passing.

Only the session's own partitions are read (ADR 0036; a table with none has every applicable
name missing). Applicability is ``Feature.applies_to`` decided by ``features.framework.feature
.not_applicable``, the function the read layer's NOT_APPLICABLE uses (ADR 0042), over the
session's reference snapshot; the population is the universe snapshot of the session; tiers are
``tasks.market.tiers`` (core: S&P 500, priority symbols, HIGH liquidity). A value is covered when
present, or null for a reason its status column gives for the session that the feature declares
as "too illiquid to price" (ADR 0042) or as an explained absence (ADR 0046: no trade, not
announced, a new listing), the same statuses the read layer shows; except that NO_TRADE never
covers a core name (a vendor-dropped AAPL bar must not pass as "no trade"). Any other missing
value is missing, never counted as zero or filled. A ``recent`` rule
grades a date instead (overdue earnings): of the names with a row, a date older than
``max_age_days`` with no ``or_value`` is missing, listed with that date (FDX on 2026-10-02: last
report 2026-06-23 and no next date, because the Nasdaq calendar had dropped it). The previous
session's shares are recomputed from its stored partitions (no new table); the nightly runs
this as the acceptance check of ``rollups`` and ``run_quality`` runs it with the rest.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.site.coverage import CoverageRule
from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.fields import REFERENCE_TABLE, ROLLUP_TABLE_PREFIX
from algotrade.data import StoreReader
from algotrade.data.reference import UNIVERSE_TABLE, companies, snapshot
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import Feature, NullReason, not_applicable
from algotrade.services.features import site_features, site_store
from algotrade_ingestion.tasks.maintenance.quality import Check
from algotrade_ingestion.tasks.market.tiers import CORE, REST, load_tiers

TIERS = (CORE, REST)
STORED_EXAMPLES = 10  # missing names kept per cell in the check's data (the email shows fewer)
ETF = "ETF"
# Explained absences that still count as a gap for a core name (ADR 0046): a large stock with
# no bar is far likelier a dropped bar than a day without a trade.
GAP_IN_CORE = frozenset({NullReason.NO_TRADE.value})


@dataclass(frozen=True)
class Cell:
    """One feature in one tier for one session: ``covered`` of ``applicable`` names have it."""

    feature: str
    tier: str
    applicable: int
    covered: int
    missing: tuple[str, ...]  # symbols, sorted, at most STORED_EXAMPLES

    @property
    def share(self) -> float | None:
        """``None`` when nothing applies (no gap to speak of), else covered / applicable."""
        return self.covered / self.applicable if self.applicable else None


def _population(reader: StoreReader, session: date) -> pd.DataFrame | None:
    """The universe of the session (instrument_id, symbol, optionable, is_etf) with the
    reference snapshot's facts: ``None`` when there is no universe or reference snapshot on or
    before the session."""
    uni, ref = snapshot(reader, UNIVERSE_TABLE, session), snapshot(reader, REFERENCE_TABLE, session)
    if uni is None or ref is None or uni.pre_snapshot or ref.pre_snapshot:
        return None
    ids = reader.table(UNIVERSE_TABLE, uni.snapshot_date)
    facts = reader.table(REFERENCE_TABLE, ref.snapshot_date)
    if ids is None or facts is None:
        return None
    pop = (
        ids[["instrument_id"]]
        .drop_duplicates()
        .merge(
            facts[["instrument_id", "symbol", "security_type", "optionable"]],
            on="instrument_id",
            how="left",
        )
    )
    pop["is_etf"] = pop["security_type"].astype(str) == ETF
    company = companies(reader, session)  # on or before the session, never a later snapshot
    sic = {}
    if company is not None and "sic" in company.columns:
        sic = dict(zip(company["instrument_id"].astype(str), company["sic"], strict=True))
    pop["sic"] = [sic.get(str(i)) for i in pop["instrument_id"]]
    for fact in ("security_type", "sic"):  # "" is null (not_applicable never rules it out)
        pop[fact] = pop[fact].map(lambda v: "" if v is None or pd.isna(v) else str(v))
    pop["optionable"] = pop["optionable"].map(lambda v: None if pd.isna(v) else bool(v))
    return pop


def _explained(
    reader: StoreReader, day: date, stored: pd.DataFrame | None, feat: Feature
) -> dict[str, str]:
    """The ids whose null the feature's status column explains on ``day`` (ADR 0042: an
    illiquid chain; ADR 0046: an explained absence), each with its status. The status is a
    sibling column of ``stored`` or another group's column, read for exactly ``day``; it covers
    an id with no row in ``stored`` too (no trade: no ``price_stats`` row)."""
    if not feat.null_status:
        return {}
    if "@" in feat.null_status:
        group, _, rest = feat.null_status.partition(".")
        column, _, version = rest.partition("@")
        status = reader.table(f"{ROLLUP_TABLE_PREFIX}{group}@{version}", day)
    else:
        status, column = stored, feat.null_status
    if status is None or column not in status.columns:
        return {}
    explains = status[column].isin({*feat.illiquid_statuses, *feat.explained_statuses})
    rows = status[explains]
    return dict(zip(rows["instrument_id"].astype(str), rows[column].astype(str), strict=True))


def _recent(
    stored: pd.DataFrame, column: str, rule: CoverageRule, day: date
) -> tuple[set[str], dict[str, str]]:
    """``covered_by = "recent"``: the ids with a ``column`` date at most ``max_age_days``
    before ``day`` or a value in ``or_value``, and the stale date (ISO) of each other id."""
    stamps = pd.to_datetime(stored[column], errors="coerce")
    recent = stamps.notna() & (stamps >= pd.Timestamp(day) - pd.Timedelta(days=rule.max_age_days))
    dates = stamps.dt.date
    if rule.or_value and rule.or_value in stored.columns:
        recent |= stored[rule.or_value].notna()
    ids = stored["instrument_id"].astype(str)
    stale = {
        i: "" if pd.isna(d) else d.isoformat()
        for i, d in zip(ids[~recent], dates[~recent], strict=True)
    }
    return set(ids[recent]), stale


def _locate(fs: FeatureSet, feature: str) -> tuple[str, str, Feature]:
    """``<group>.<column>`` -> its stored table, column and declaration."""
    group, _, column = feature.partition(".")
    found = [
        f for f in fs.features.values() if f.group.partition("@")[0] == group and f.name == column
    ]
    if not found:
        raise ValueError(f"coverage: {feature!r} is not a stored feature of the catalogue")
    return fs.table(group), column, found[0]


def _covered(
    reader: StoreReader,
    stored: pd.DataFrame | None,
    column: str,
    feat: Feature,
    rule: CoverageRule,
    day: date,
) -> tuple[set[str], set[str] | None, dict[str, str], set[str]]:
    """The covered ids of the session's partition, the ids graded at all (``None``: every
    applicable name; "recent" grades only the names with a row, none without a partition: the
    row rule reports that gap), the stale date of each "recent" id that is not covered, and
    the ids covered only by a status that is still a gap in the core tier (``GAP_IN_CORE``)."""
    recent = rule.covered_by == "recent"
    if recent or rule.covered_by == "row":
        explained: dict[str, str] = {}
    else:
        explained = _explained(reader, day, stored, feat)
    core_gaps = {i for i, why in explained.items() if why in GAP_IN_CORE}
    if stored is None or column not in stored.columns:
        return set(explained), (set() if recent else None), {}, core_gaps
    ids = stored["instrument_id"].astype(str)
    if recent:
        have, stale = _recent(stored, column, rule, day)
        return have, set(ids), stale, set()
    if rule.covered_by == "row":
        return set(ids), None, {}, set()
    valued = set(ids[stored[column].notna()])
    return valued | set(explained), None, {}, core_gaps - valued


def cells(
    reader: StoreReader,
    day: date,
    rules: tuple[CoverageRule, ...],
    priority_symbols: tuple[str, ...],
    fs: FeatureSet,
) -> list[Cell] | None:
    """Every rule's cells (core, rest) for ``day``; ``None`` without a universe to measure."""
    pop = _population(reader, day)
    if pop is None:
        return None
    tiers = load_tiers(reader, day, priority_symbols)
    symbols = pop["symbol"].astype(str).to_numpy()
    pop = pop.assign(
        tier=[
            tiers.tier(i, s) for i, s in zip(pop["instrument_id"].astype(str), symbols, strict=True)
        ]
    )
    out: list[Cell] = []
    for rule in rules:
        table, column, feat = _locate(fs, rule.feature)
        have, scope, stale, core_gaps = _covered(
            reader, reader.table(table, day), column, feat, rule, day
        )
        applies = [
            not not_applicable([feat.applies_to], opt, kind, sic)
            for opt, kind, sic in zip(
                pop["optionable"], pop["security_type"], pop["sic"], strict=True
            )
        ]
        for tier in TIERS:
            mine = pop[(pop["tier"] == tier) & pd.Series(applies, index=pop.index)]
            if scope is not None:
                mine = mine[mine["instrument_id"].astype(str).isin(scope)]
            ids = mine["instrument_id"].astype(str)
            covered = have - core_gaps if tier == CORE else have
            out_ids = ids[~ids.isin(covered)]
            syms = mine.loc[out_ids.index, "symbol"].astype(str)
            gone = [
                f"{sym} (last {stale[i]})" if stale.get(i) else sym
                for i, sym in zip(out_ids, syms, strict=True)
            ]
            out.append(
                Cell(
                    rule.feature,
                    tier,
                    len(mine),
                    len(mine) - len(gone),
                    tuple(sorted(gone))[:STORED_EXAMPLES],
                )
            )
    return out


def _previous(
    reader: StoreReader, session: date, fs: FeatureSet, rule: CoverageRule
) -> date | None:
    """The latest session before ``session`` with a partition of the rule's own table (one
    feature's table may lack a session the others have: chains run only for the latest)."""
    days = [d for d in reader.dates(_locate(fs, rule.feature)[0]) if d < session]
    return max(days) if days else None


def _percent(share: float | None) -> str:
    return "n/a" if share is None else f"{share:.1%}"


def check_coverage(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """One check per configured feature: FAIL / WARN (by the rule's level) when a tier's
    share is under its minimum or fell more than ``max_drop`` since the previous session,
    else PASS. ``data`` carries the cells (and the previous shares) for the report."""
    fs = site_features(site_store(None))
    today = cells(reader, session, s.coverage, s.cboe_priority_symbols, fs)
    if today is None:
        return [Check("coverage", "FAIL", "no universe or reference snapshot to measure against")]
    days = {r.feature: _previous(reader, session, fs, r) for r in s.coverage}
    prev: dict[tuple[str, str], float | None] = {}
    for day in {d for d in days.values() if d}:
        rules = tuple(r for r in s.coverage if days[r.feature] == day)
        prev |= {
            (c.feature, c.tier): c.share
            for c in cells(reader, day, rules, s.cboe_priority_symbols, fs) or []
        }
    checks = []
    for rule in s.coverage:
        before_day = days[rule.feature]
        mine = [c for c in today if c.feature == rule.feature]
        status, notes = "PASS", []
        rows: list[dict[str, Any]] = []
        for c in mine:
            floor = rule.core_min if c.tier == CORE else rule.rest_min
            share, was = c.share, prev.get((c.feature, c.tier))
            breaches = []
            if share is not None and share < floor:
                breaches.append(f"{_percent(share)} < min {floor:.0%}")
            if share is not None and was is not None and was - share > rule.max_drop:
                breaches.append(f"fell {was - share:.1%} from {_percent(was)}")
            if breaches:
                notes.append(f"{c.tier} {'; '.join(breaches)}")
                level = rule.level_of(c.tier)
                status = "FAIL" if "FAIL" in (status, level) else "WARN"
            rows.append(
                {
                    "tier": c.tier,
                    "applicable": c.applicable,
                    "covered": c.covered,
                    "share": share,
                    "previous": was,
                    "ok": not breaches,
                    "missing": list(c.missing),
                }
            )
        figures = ", ".join(f"{c.tier} {_percent(c.share)} of {c.applicable}" for c in mine)
        if rule.covered_by == "recent":
            or_value = f" and no {rule.or_value}" if rule.or_value else ""
            notes.append(f"overdue: over {rule.max_age_days} days since the date{or_value}")
        if before_day is None:
            notes.append("no earlier partition: drop not checked")
        detail = f"{figures}" + (f" ({'; '.join(notes)})" if notes else "")
        checks.append(
            Check(
                f"coverage_{rule.feature}",
                status,
                detail,
                data={"cells": rows, "previous_session": str(before_day) if before_day else ""},
            )
        )
    return checks
