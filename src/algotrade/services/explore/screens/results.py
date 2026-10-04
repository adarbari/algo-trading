"""Screener configs with their schedule and latest run, and a screen's saved results for a
session (rows with decision, score, reasons and values; the run's audit and coverage)."""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import RULES_IMPL
from algotrade.config.user import SITE_USER
from algotrade.data.reference import resolver
from algotrade.services.explore.configs import ConfigSummary, config_list, resolved
from algotrade.services.explore.store import (
    NotFoundError,
    Page,
    ReadStore,
    paginate,
    partition_for,
    record,
)
from algotrade.services.screening.run import run_job_name
from algotrade.services.views import to_value
from algotrade.storage.tables.schemas import result_table

SCREENER = "screener"
ROW_FIELDS = (
    "instrument_id",
    "decision",
    "score",
    "reasons",
    "user_id",
    "config_id",
    "config_hash",
)


@dataclass(frozen=True)
class ScreenConfig:
    config: ConfigSummary
    latest_run: str | None
    latest_session: date | None
    latest_status: str | None


def _owners(store: ReadStore) -> list[str]:
    """Whose runs to show: the user's own, then the site's (presets run as ``site``)."""
    return list(dict.fromkeys([store.user.user_id, SITE_USER]))


def screen_configs(store: ReadStore) -> list[ScreenConfig]:
    out = []
    for config in config_list(store, SCREENER):
        owner = SITE_USER if config.scope == "site" else config.scope
        runs = store.reader.runs(run_job_name(config.config_id, owner))
        last = runs[-1] if runs else None
        out.append(
            ScreenConfig(
                config,
                last.run_id if last else None,
                last.session_date if last else None,
                last.status.value if last else None,
            )
        )
    return out


@dataclass(frozen=True)
class ScreenResults:
    config_id: str
    user: str
    session: date
    run_id: str | None
    decisions: dict[str, int]
    audit: dict[str, Any]  # the run record's stats: coverage, selection audit, universe, hash
    page: Page[dict[str, Any]]


@dataclass(frozen=True)
class RunRows:
    """A screen's stored rows of its latest run in one session: whose run, which, the rows."""

    config: ResolvedConfig
    owner: str
    session: date
    run_id: str
    rows: pd.DataFrame


def run_rows(store: ReadStore, config_id: str, on: date | None) -> RunRows:
    """The rows the screen saved for the latest session on or before ``on`` (the user's run,
    else the site's). ``NotFoundError``: not a screener, or nothing stored."""
    config = resolved(store, config_id)
    if config.config.kind != SCREENER:
        raise NotFoundError(f"{config_id} is a {config.config.kind}, not a screener")
    rules = config.config.impl == RULES_IMPL  # one table holds every rule screen's rows
    table = result_table("rule_screen" if rules else config.config.impl)
    session = partition_for(store.reader, table, on)
    frame = store.reader.table(table, session)
    if frame is None:  # pragma: no cover - partition_for found the partition
        raise NotFoundError(f"{table}: nothing stored for {session}")
    for owner in _owners(store):
        rows = frame[(frame["config_id"] == config_id) & (frame["user_id"] == owner)]
        if len(rows):
            return RunRows(config, owner, session, str(rows["run_id"].iloc[0]), rows)
    raise NotFoundError(f"no results of {config_id} stored for {session}")


def screen_results(
    store: ReadStore,
    config_id: str,
    on: date | None,
    decision: str | None,
    page: int,
    size: int,
) -> ScreenResults:
    """The rows the screen saved for the latest session on or before ``on`` (the user's run,
    else the site's), filtered by ``decision``, sorted by score (best first)."""
    found = run_rows(store, config_id, on)
    rows, owner, run_id, session = found.rows, found.owner, found.run_id, found.session
    names = resolver(store.reader, session)
    items = []
    for row in rows.sort_values("score", ascending=False, kind="stable").to_dict("records"):
        iid = str(row["instrument_id"])
        items.append(
            {
                "instrument_id": iid,
                "symbol": names.symbol_for(iid),
                "decision": str(row["decision"]),
                "score": to_value(row.get("score")),
                "reasons": to_value(row.get("reasons")),
                "values": record(row, ROW_FIELDS),
            }
        )
    counts = Counter(str(d) for d in rows["decision"])
    if decision:
        items = [i for i in items if str(i["decision"]).casefold() == decision.casefold()]
    audit = next(
        (r.stats for r in store.reader.runs(run_job_name(config_id, owner)) if r.run_id == run_id),
        {},
    )
    return ScreenResults(
        config_id, owner, session, run_id, dict(counts), audit, paginate(items, page, size)
    )
