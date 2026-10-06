"""Data-quality checks: fail loudly instead of screening on bad or missing data.

Each check is PASS, WARN or FAIL with a detail line. The nightly runs them as the acceptance
checks of the steps that wrote the data (ADR 0039, ``workflows/nightly/nightly.py``): a FAIL
fails that step, which holds back the steps that need it. The ``quality`` task runs them all
for a session by hand (any FAIL makes that run PARTIAL). Thresholds come from
``config/site/sources.toml`` ``[quality]``.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.instruments import market_id
from algotrade.data import StoreReader
from algotrade.data.chains import chain_status
from algotrade.data.reference import snapshot
from algotrade.services.features import site_features
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.reference.classify import security_type

TASK = "data_quality"


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str
    pending: bool = False  # a FAIL that only means "the source has not published it yet" (ADR 0043)
    data: dict[str, Any] = field(default_factory=dict)  # figures behind it (coverage: its cells)


def _rows(reader: StoreReader, table: str, day: date | None) -> int | None:
    if day is None:
        return None
    frame = reader.table(table, day)
    return None if frame is None else len(frame)


def _latest(reader: StoreReader, table: str, session: date) -> date | None:
    """The partition a read for ``session`` sees; ``None`` if every one is after it."""
    snap = snapshot(reader, table, session)
    return None if snap is None or snap.pre_snapshot else snap.snapshot_date


def _previous(reader: StoreReader, table: str, session: date) -> date | None:
    dates = [d for d in reader.dates(table) if d < session]
    return dates[-1] if dates else None


BARS_TASK = "daily_bars"  # the bars task's run-record job name (tasks/market/bars.py)
NOT_PUBLISHED = "NOT_PUBLISHED"  # the bars task's item status (tasks/market/bars.py)


def _bars_not_published(reader: StoreReader, session: date) -> bool:
    """Whether the latest bars run for ``session`` found it not published yet (the vendor
    answers for the session before: ``tasks/market/bars.py``)."""
    runs = [r for r in reader.runs(BARS_TASK, session) if r.finished_at is not None]
    if not runs:
        return False
    latest = max(runs, key=lambda r: r.finished_at or r.started_at)
    return str(latest.items.get(session.isoformat(), "")).startswith(NOT_PUBLISHED)


def check_bars(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    latest = _latest(reader, "bars/1d", session)
    if latest is None:
        return [Check("bars_present", "FAIL", "no bars stored (backfill not run)")]
    checks = [
        Check(
            "bars_fresh",
            "PASS" if latest == session else "FAIL",
            f"latest bars session {latest}, expected {session}",
            pending=latest != session and _bars_not_published(reader, session),
        )
    ]
    today, before = (
        _rows(reader, "bars/1d", latest),
        _rows(reader, "bars/1d", _previous(reader, "bars/1d", latest)),
    )
    if today and before:
        drop = 1 - today / before
        status = "FAIL" if drop > s.max_bar_count_drop else "PASS"
        checks.append(
            Check(
                "bars_count",
                status,
                f"{today} bars vs {before} the session before ({drop:+.1%} drop)",
            )
        )
    return checks


def check_bars_resolved(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The share of the session's bars whose ticker the resolver did not know (the latest
    bars run for the session); nothing when the session's bars were stored earlier."""
    runs = [r for r in reader.runs(BARS_TASK, session) if r.finished_at is not None]
    rows = _rows(reader, "bars/1d", session)
    if not runs or not rows:
        return []
    latest = max(runs, key=lambda r: r.finished_at or r.started_at)
    unresolved = int(latest.stats.get("unresolved", 0))
    share = unresolved / rows
    return [
        Check(
            "bars_resolved",
            "FAIL" if share > s.max_bar_unresolved else "PASS",
            f"{unresolved} of {rows} bars unresolved ({share:.1%}, max {s.max_bar_unresolved:.0%})",
        )
    ]


def check_universe(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    latest = _latest(reader, "universe", session)
    if latest is None:
        return [Check("universe_present", "FAIL", "no universe snapshot")]
    today, before = (
        _rows(reader, "universe", latest),
        _rows(reader, "universe", _previous(reader, "universe", latest)),
    )
    if not today:
        return [Check("universe_present", "FAIL", f"empty universe on {latest}")]
    if not before:
        return [Check("universe_size", "PASS", f"{today} instruments (no earlier snapshot)")]
    change = today / before - 1
    status = "FAIL" if abs(change) > s.max_universe_change else "PASS"
    return [
        Check(
            "universe_size",
            status,
            f"{today} vs {before} instruments ({change:+.1%}); "
            "an unexplained jump means UNIVERSE INCOMPLETE",
        )
    ]


def check_reference_classification(
    reader: StoreReader, session: date, s: SourcesSettings
) -> list[Check]:
    """FAIL when the vendor's security type and our name rules disagree on too many ACTIVE
    rows (ADR 0045): a vendor that retyped its list, or a name rule gone wrong, moves the
    universe silently. Counts the rows typed by ``name_over_vendor`` and those whose stored
    type differs from the name rule's (a vendor type that stood, ``CEF`` for a fund, counts)."""
    latest = _latest(reader, "instruments/reference", session)
    frame = None if latest is None else reader.table("instruments/reference", latest)
    if frame is None or frame.empty or "security_type_source" not in frame.columns:
        return [Check("reference_classification", "FAIL", "no reference snapshot to classify")]
    active = frame[frame["status"].eq("ACTIVE")]
    named = pd.Series(
        [
            security_type(str(n), str(y), bool(e))
            for n, y, e in zip(active["name"], active["symbol"], active["is_etf"], strict=True)
        ],
        index=active.index,
    )
    from_vendor = active["security_type_source"].isin(["vendor", "name_over_vendor"])
    over = int(active["security_type_source"].eq("name_over_vendor").sum())
    disagree = int((from_vendor & active["security_type"].ne(named)).sum()) + over
    total = len(active)
    return [
        Check(
            "reference_classification",
            "FAIL"
            if disagree / total > s.max_type_disagreement or over / total > s.max_name_over_vendor
            else "PASS",
            f"{disagree} of {total} ACTIVE rows ({disagree / total:.1%}) typed differently by "
            f"the vendor and the name rules, {over} ({over / total:.1%}) decided by the name "
            f"(max {s.max_type_disagreement:.0%} and {s.max_name_over_vendor:.0%})",
            data={"disagreements": disagree, "name_over_vendor": over, "active": total},
        )
    ]


# Chain statuses (``tasks/market/option_chains``) by what they say about the night's fetch:
# a failed or missing fetch is a source problem (FAIL); a stale chain is the feed serving an
# older session (FAIL above the share: a later retry usually gets the session's chains); the
# rest are answers.
FETCH_FAILURES = ("FETCH_ERROR", "NOT_ATTEMPTED")  # FETCH_ERROR includes an open circuit
STALE = "STALE_DATA"
EXAMPLES = 8  # stale core names listed in the detail
REPORTED = ("OK", "STALE_DATA", "NO_CHAIN", "NO_STANDARD_SERIES")


def check_chains(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    status_frame = chain_status(reader, session)
    if status_frame is None or status_frame.empty:
        return [Check("chains_present", "FAIL", f"no option chains for {session}")]
    labels = status_frame["status"].astype(str).str.split(":", n=1).str[0].str.strip()
    total = len(labels)
    counts = labels.value_counts()
    failed = int(labels.isin(FETCH_FAILURES).sum())
    breakdown = ", ".join(f"{k} {int(counts.get(k, 0))}" for k in REPORTED)
    detail = f"of {total} underlyings: {breakdown}, fetch failures {failed}"
    return [
        Check(
            "chains_fetch",
            "FAIL" if failed / total > s.max_chain_fetch_failures else "PASS",
            f"{failed / total:.1%} failed to fetch "
            f"(max {s.max_chain_fetch_failures:.0%}); {detail}",
        ),
        _stale_check(status_frame, labels, "core", s.max_chain_stale_share_core, detail),
        _stale_check(status_frame, labels, "rest", s.max_chain_stale_share, detail),
    ]


def _stale_check(
    frame: pd.DataFrame, labels: pd.Series, tier: str, limit: float, detail: str
) -> Check:
    """``chains_stale_<tier>``: the share of the tier's chains that are STALE_DATA, FAIL above
    ``limit``. The tier is the one stored with each status row at fetch time (rows from before
    the column existed count as rest); stale core names are listed."""
    stored = frame["tier"] if "tier" in frame.columns else pd.Series("rest", index=frame.index)
    in_tier = stored.fillna("rest").astype(str) == tier
    total = int(in_tier.sum())
    if tier == "core" and total == 0 and "tier" in frame.columns:
        # a tiered status with no core name means the tier inputs were missing: no gate
        return Check(
            "chains_stale_core", "FAIL", f"no core names in a tiered chain status; {detail}"
        )
    stale = in_tier & (labels == STALE)
    count = int(stale.sum())
    share = count / total if total else 0.0
    names = ""
    if tier == "core" and count:
        listed = frame.loc[stale, "symbol"].astype(str).sort_values().head(EXAMPLES).tolist()
        names = f"; stale: {', '.join(listed)}" + (" ..." if count > EXAMPLES else "")
    return Check(
        f"chains_stale_{tier}",
        "FAIL" if share > limit else "PASS",
        f"{count} of {total} {tier} chains stale ({share:.1%}, max {limit:.0%}){names}; {detail}",
        pending=True,  # Cboe has not rolled to the session yet (ADR 0043)
        data={"share": share},
    )


def check_earnings(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    rows = _rows(reader, "events/earnings", _latest(reader, "events/earnings", session))
    if not rows:
        return [Check("earnings_present", "FAIL", "no earnings calendar stored")]
    return [Check("earnings_present", "PASS", f"{rows} upcoming earnings rows")]


VERIFICATION = "verification/ibkr"
GRADED = ("PASS", "WARN", "FAIL")  # NA checks (either side without a value) are not graded


def check_verification(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The live verification vs IBKR (``verify``): FAIL above ``max_verify_failures`` of the
    graded checks failing, WARN on any FAIL. Nothing when ``[ibkr]`` is disabled."""
    if not s.vendor("ibkr").enabled:
        return []
    frame = reader.table(VERIFICATION, session)
    if frame is None or frame.empty:
        return [
            Check(
                "verification",
                "WARN",
                f"no verification vs IBKR for {session} (IB Gateway not reachable?)",
            )
        ]
    counts = frame["status"].astype(str).value_counts()
    graded = sum(int(counts.get(k, 0)) for k in GRADED)
    failed = int(counts.get("FAIL", 0))
    share = failed / graded if graded else 0.0
    status = "FAIL" if share > s.max_verify_failures else "WARN" if failed else "PASS"
    breakdown = ", ".join(f"{k} {int(counts.get(k, 0))}" for k in (*GRADED, "NA"))
    names = frame.loc[frame["status"] == "FAIL", "symbol"].astype(str).unique()[:5]
    worst = f"; failing: {', '.join(names)}" if failed else ""
    return [
        Check(
            "verification",
            status,
            f"{share:.1%} of {graded} graded checks failed vs IBKR "
            f"(max {s.max_verify_failures:.0%}); {breakdown}{worst}",
        )
    ]


def check_market_rollups(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The acceptance of ``market-rollups`` (ADR 0047): each market group has its one
    ``MKT:US`` row stored for ``session``; FAIL names the groups without (a group with no
    input for the session writes nothing). PASS with no market group declared."""
    groups = [g for g in site_features().groups.values() if g.entity == "market"]
    missing = []
    for group in groups:
        frame = reader.table(group.table, session)
        if frame is None or list(frame["instrument_id"]) != [market_id("US")]:
            missing.append(group.key)
    if missing:
        return [
            Check(
                "market_rollups",
                "FAIL",
                f"no {market_id('US')} row for {session}: {', '.join(missing)}",
            )
        ]
    return [
        Check("market_rollups", "PASS", f"{len(groups)} market groups with their row for {session}")
    ]


CHECKS: tuple[Callable[[StoreReader, date, SourcesSettings], list[Check]], ...] = (
    check_universe,
    check_bars,
    check_bars_resolved,
    check_chains,
    check_earnings,
    check_verification,
)


def run_quality(ctx: TaskContext, session: date) -> RunRecord:
    # imported here: coverage.py imports ``Check`` from this module
    from algotrade_ingestion.tasks.maintenance.coverage import check_coverage  # noqa: PLC0415

    with IngestRun(ctx, TASK, session) as run:
        checks = [
            c for fn in (*CHECKS, check_coverage) for c in fn(ctx.reader, session, ctx.settings)
        ]
        for check in checks:
            run.record_item(check.name, check.status)
        failed = [c.name for c in checks if c.status == "FAIL"]
        for name in failed:
            run.partial(f"check {name} failed")
        run.stats.update(checks=[asdict(c) for c in checks], failed=failed)
    return run.record
