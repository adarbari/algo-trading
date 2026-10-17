"""Share counts, basic financials and financial statement lines from SEC company facts as
two L1 tables (``instruments/shares``, phase 2b.4, with revenue, net income and diluted EPS for
``financials@v2``; ``instruments/statements``, ADR 0067), written from ONE fetch of each
company's document.

- CIK per instrument: the latest ``instruments/company`` snapshot on or before the session
  (the reference's CIK or the SEC ticker map, chosen by ``company_details``), else the
  reference's own CIK.
- Share classes: companyfacts has no class-specific counts (it drops dimensional facts), so
  every instrument with the same CIK (GOOGL and GOOG, BRK.A and BRK.B) gets the CIK's facts,
  the company total. A class-specific source would win once one exists.
- Incremental: a CIK is fetched when never fetched or past its refresh slot
  (``refresh.due_keys``: once per ``[sec_edgar] facts_refresh_days``, spread over the window
  by CIK); ``force`` refetches all, ``limit`` caps a run. Each run stores only facts not
  stored yet, plus a ``checked`` marker per instrument of every fetched CIK (``fetched_on``),
  so a CIK without facts (404, a fund) is not refetched every night. An instrument new to a
  CIK that is not due gets the CIK's stored facts copied.
- Two tables, one fetch: a CIK is due when EITHER table is due (its older ``fetched_on`` decides;
  a CIK with no marker in one of them is new there), so a table that failed to stage for a CIK
  that the other table stored is due again the next night, not in 30 days. A table's rows are
  staged separately, the shares first.
- Priority: WHICH CIKs are fetched first (the statements backlog before the nightly cap, and
  ``limit``) is ``priority_order``: tier 0 the event scope (list, tier A / B, fund references),
  tier 1 the current S&P 500, tier 2 the rest; inside tiers 1 and 2 optionable and liquid names
  (``optionable`` of the reference, ``adv_usd_20d`` at least ``[sec_edgar]
  statements_priority_min_adv_usd``) first, then
  optionable, then the others, each by dollar volume then market cap (shares x close) descending,
  ties by CIK; a CIK takes its best instrument's key. It only reorders:
  what is due, the cap's exemptions and ``force`` do not change, and a missing input (no list,
  no membership snapshot, no roll-up) leaves that tier empty, the order falling back to CIK.
- Per-CIK rows are staged and published as one partition per table; a crashed run resumes
  (CIKs it already fetched are skipped).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade.data import StoreReader
from algotrade.data.reference import instruments, snapshot
from algotrade.data.rollups import rollup_as_of
from algotrade.data.shares import CHECKED, DATES, KEY, TABLE, stored_shares
from algotrade.data.statements.reading import KEY as STATEMENT_KEY
from algotrade.data.statements.reading import TABLE as STATEMENTS
from algotrade.data.statements.reading import light_statements, stored_statements
from algotrade.services.events.scope import scoped_instruments
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.refresh import due_keys
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "shares"
COMPANY = "instruments/company"
CHECKPOINT_EVERY = 100
FUNDAMENTALS = "rollups/instrument/fundamentals@v3"
PRICE_STATS = "rollups/instrument/price_stats@v2"
CARRY = "carry"  # staging key for facts copied to instruments new to a CIK


@dataclass(frozen=True)
class SharesSources:
    facts: Source  # SecCompanyFacts
    refresh_days: int = 30
    backfill_per_night: int = 400  # CIKs with shares but no statements fetched a night (0: no cap)
    liquid_adv_usd: float = (
        10_000_000.0  # 20-day dollar volume from which an optionable name is liquid
    )


@dataclass(frozen=True)
class Target:
    """One table the task writes from the fetched document."""

    table: str
    parsed: str  # its frame in ``Normalized.parsed``
    key: list[str]
    # instrument_id, cik, concept, fetched_on of every stored row, nothing else (not deduplicated:
    # what is due needs only a maximum per CIK)
    light: Callable[[StoreReader], pd.DataFrame]
    keys: Callable[[StoreReader, list[str]], pd.DataFrame]  # the key rows of instruments
    donors: Callable[[StoreReader, list[str]], pd.DataFrame]  # full stored rows of instruments


def _share_rows(reader: StoreReader, ids: list[str]) -> pd.DataFrame:
    stored = stored_shares(reader)
    return stored[stored["instrument_id"].isin(ids)]


TARGETS = (
    Target(
        TABLE,
        "shares",
        KEY,
        lambda reader: stored_shares(reader)[["instrument_id", "cik", "concept", "fetched_on"]],
        _share_rows,
        _share_rows,
    ),
    Target(
        STATEMENTS,
        "statements",
        STATEMENT_KEY,
        light_statements,
        lambda reader, ids: stored_statements(reader, instruments=ids, columns=["fetched_on"]),
        lambda reader, ids: stored_statements(reader, instruments=ids),
    ),
)


def instrument_ciks(reader: StoreReader, session: date) -> pd.DataFrame:
    """``instrument_id``, ``symbol``, ``cik`` for every instrument with a known CIK."""
    reference = instruments(reader, session)
    own = (
        reference["cik"].map(pad_cik)
        if "cik" in reference.columns
        else pd.Series(None, index=reference.index, dtype=object)
    )
    out = pd.DataFrame(
        {
            "instrument_id": reference["instrument_id"].astype(str),
            "symbol": reference["symbol"].astype(str),
            "cik": own,
        }
    )
    snap = snapshot(reader, COMPANY, session)
    company = (
        None if snap is None or snap.pre_snapshot else reader.table(COMPANY, snap.snapshot_date)
    )
    if company is not None and not company.empty:
        sec = company.set_index(company["instrument_id"].astype(str))["cik"].map(pad_cik)
        mapped = out["instrument_id"].map(sec)
        out["cik"] = mapped.where(mapped.notna(), out["cik"])
    return out[out["cik"].notna()].reset_index(drop=True)


def _rows(
    facts: pd.DataFrame, members: pd.DataFrame, fetched_on: date, key: list[str] = KEY
) -> pd.DataFrame:
    """One CIK's facts for each of its instruments, plus a ``checked`` marker each."""
    marker = pd.DataFrame(
        [{"concept": CHECKED, "tag": None, "period_start": None, "period_end": None, "filed": None}]
    )
    out = pd.concat([facts.drop(columns=["cik"], errors="ignore"), marker], ignore_index=True)
    for column in DATES:
        if column in out.columns:
            day = pd.to_datetime(out[column]).dt.date
            out[column] = day.astype(object).where(out[column].notna(), None)
    # Two filings on one day for one period and tag (a same-day amendment): the later listed
    # wins; other tags of the period are kept (the rollups rank them).
    out = out.drop_duplicates(key[1:], keep="last")
    out = members[["instrument_id", "symbol", "cik"]].merge(out, how="cross")
    out["fetched_on"] = fetched_on
    return out


def _fetch(
    run: IngestRun,
    source: Source,
    cik: str,
    members: pd.DataFrame,
    known: Mapping[str, set[tuple[object, ...]]],
) -> str:
    """One document, both tables: each table's new rows are staged in turn, so a failure to
    stage the statements leaves the shares staged (and the statements due again)."""
    normalized = None
    try:
        normalized = run.fetch(source, FetchRequest(cik, session_date=run.session))
    except NoResponseError:
        parsed: Mapping[str, pd.DataFrame] = {}
        status = "NO_FACTS"  # no XBRL facts under this CIK (common for funds)
    else:
        parsed = normalized.parsed if normalized is not None else {}
        sizes = {t.parsed: len(parsed.get(t.parsed, ())) for t in TARGETS}
        status = f"OK: {sizes['shares']} facts, {sizes['statements']} statements"
        if not any(sizes.values()):
            status = "NO_SHARE_FACTS"
    for target in TARGETS:
        facts = parsed.get(target.parsed)
        if facts is None and normalized is not None:
            # A document that came but whose table did not parse: no marker (the CIK stays due
            # for it), raised after the earlier tables staged.
            raise ValueError(f"{target.parsed} could not be parsed from the document")
        facts = pd.DataFrame(columns=["concept"]) if facts is None else facts
        rows = _rows(facts, members, run.session, target.key)
        new = [tuple(r) for r in rows[target.key].astype(object).itertuples(index=False)]
        fresh = [k not in known[target.table] or k[1] == CHECKED for k in new]
        run.stage(target.table, cik, _typed(rows[fresh]), source.name)
    return status


def _typed(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    for column in ("fy", "class_values"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").astype("Int64")
    return out.astype(object).where(out.notna(), None)


def _carry(
    reader: StoreReader, target: Target, light: pd.DataFrame, ids: pd.DataFrame, fetched: set[str]
) -> pd.DataFrame:
    """Stored facts of a CIK copied to its instruments that have none (a new listing or
    class), for CIKs not fetched this run; only the rows of one stored instrument per CIK are
    read in full."""
    stored = light[light["concept"] != CHECKED]
    if stored.empty:
        return stored
    have = set(stored["instrument_id"].astype(str))
    new = ids[~ids["instrument_id"].isin(have) & ~ids["cik"].isin(fetched)]
    donors = stored[stored["cik"].isin(new["cik"])].drop_duplicates("cik")
    if donors.empty:
        return donors
    facts = target.donors(reader, list(donors["instrument_id"].astype(str)))
    facts = facts[facts["concept"] != CHECKED]
    by_cik = facts.drop_duplicates(["cik", *target.key[1:]])
    by_cik = by_cik.drop(columns=["instrument_id", "symbol"], errors="ignore")
    return new[["instrument_id", "symbol", "cik"]].merge(by_cik, on="cik", how="inner")


def _fetched(light: pd.DataFrame) -> dict[str, date]:
    """Per CIK its latest ``fetched_on`` (a maximum over every stored row)."""
    if light.empty:
        return {}
    latest = light.groupby("cik")["fetched_on"].max()
    return {str(c): pd.Timestamp(v).date() for c, v in latest.items()}


@dataclass(frozen=True)
class Standing:
    """What orders one instrument: ``optionable`` (reference flag; ``None`` unknown counts as
    not), ``adv_usd`` (20-day dollar volume) and ``market_cap`` (0: not stored)."""

    optionable: bool | None = None
    adv_usd: float = 0.0
    market_cap: float = 0.0


def _key(
    instrument_id: str, scope: set[str], sp500: set[str], standing: Standing, liquid: float
) -> tuple[float, ...]:
    """Sort key of one instrument: tier (scope 0, S&P 500 1, rest 2), then optionable and liquid
    (0), optionable (1), not (2), then dollar volume and market cap descending."""
    tier = 0 if instrument_id in scope else 1 if instrument_id in sp500 else 2
    grade = 2 if not standing.optionable else 0 if standing.adv_usd >= liquid else 1
    return (tier, grade if tier else 0, -standing.adv_usd, -standing.market_cap)


def priority_order(
    ciks: list[str],
    scope: set[str],
    sp500: set[str],
    standing: Mapping[str, Standing],
    cik_of: Mapping[str, str],
    liquid_adv_usd: float = 10_000_000.0,
) -> list[str]:
    """``ciks`` by priority: tier 0 a CIK holding a ``scope`` instrument, tier 1 an ``sp500``
    one, tier 2 the rest; inside a tier (scope excepted) optionable and liquid, optionable,
    the others; then dollar volume and market cap descending, ties by CIK. A CIK takes its best
    instrument's key. ``cik_of``: instrument id -> CIK. Deterministic; the same CIKs, reordered;
    an instrument without standing sorts after those with it."""
    best: dict[str, tuple[float, ...]] = {}
    for instrument_id, cik in cik_of.items():
        key = _key(
            instrument_id, scope, sp500, standing.get(instrument_id, Standing()), liquid_adv_usd
        )
        if cik not in best or key < best[cik]:
            best[cik] = key
    return sorted(ciks, key=lambda c: (*best.get(c, (2, 2, 0.0, 0.0)), c))


def _standing(reader: StoreReader, session: date, reference: pd.DataFrame) -> dict[str, Standing]:
    """Optionable (the reference snapshot), 20-day dollar volume and market cap (shares x close)
    from the newest stored roll-ups on or before ``session``; a missing input is 0 / unknown."""
    out: dict[str, dict[str, float | bool | None]] = {}
    if "optionable" in reference.columns:
        for i, o in zip(reference["instrument_id"], reference["optionable"], strict=True):
            out.setdefault(str(i), {})["optionable"] = None if pd.isna(o) else bool(o)
    stats = rollup_as_of(reader, PRICE_STATS, session)
    shares = rollup_as_of(reader, FUNDAMENTALS, session)
    px = n = pd.Series(dtype=float)
    if stats is not None:
        frame = stats[1].set_index(stats[1]["instrument_id"].astype(str))
        px = frame["close"] if "close" in frame.columns else px
        if "adv_usd_20d" in frame.columns:
            for i, v in frame["adv_usd_20d"].dropna().items():
                out.setdefault(str(i), {})["adv_usd"] = float(v)
    if shares is not None and "shares_outstanding" in shares[1].columns:
        n = shares[1].set_index(shares[1]["instrument_id"].astype(str))["shares_outstanding"]
    for i, v in (n * px).dropna().items():
        out.setdefault(str(i), {})["market_cap"] = float(v)
    return {i: Standing(**v) for i, v in out.items()}  # type: ignore[arg-type]


def _prioritised(
    ctx: TaskContext, ids: pd.DataFrame, session: date, ciks: list[str], liquid_adv_usd: float
) -> list[str]:
    """``ciks`` in the order the backlog is fetched: the owner's scope, the S&P 500 (the
    reference's ``in_sp500``), the rest by liquidity and market cap. Every input is read as of
    the day BEFORE ``session`` (the rule of ``tasks/market/tiers.py``): a rerun after tonight's
    roll-ups exist must pick the same CIKs as the first attempt. Every input is optional: a
    missing one leaves its tier empty."""
    asof = session - timedelta(days=1)
    cik_of = dict(zip(ids["instrument_id"], ids["cik"], strict=True))
    scope = set(scoped_instruments(ctx.reader, ctx.configs, asof).instrument_ids)
    reference = instruments(ctx.reader, session)
    flag = reference["in_sp500"] if "in_sp500" in reference.columns else pd.Series([], dtype=bool)
    flagged = flag.fillna(False).astype(bool).to_numpy()
    sp500 = set(reference["instrument_id"].astype(str)[flagged]) if len(flag) else set()
    standing = _standing(ctx.reader, asof, reference)
    return priority_order(ciks, scope, sp500, standing, cik_of, liquid_adv_usd)


def _due(
    ciks: list[str],
    fetched: list[dict[str, date]],
    session: date,
    sources: SharesSources,
    force: bool,
    priority: list[str] | None = None,
) -> tuple[list[str], int]:
    """The CIKs to fetch and how many of the statements backlog the nightly cap defers. A CIK
    is due when either table is (the older latest fetch decides; one table's marker missing
    makes it new there). Only the backlog (shares stored, statements never) is capped, in its
    ``priority`` order (default: CIK order): a CIK new to both or due for shares is never
    deferred, and the cap defers the lowest priority."""
    both = {c: min(f[c] for f in fetched) for c in fetched[0] if all(c in f for f in fetched)}
    due = due_keys(ciks, both, session, sources.refresh_days, force)
    rank = {c: i for i, c in enumerate(priority or [])}
    new = sorted(
        (c for c in due if force or c not in both), key=lambda c: (rank.get(c, len(rank)), c)
    )
    due = new + [
        c for c in due if not force and c in both
    ]  # new to a table by priority, then the stalest
    cap = sources.backfill_per_night
    if force or cap <= 0:
        return due, 0
    shares_due = set(due_keys(ciks, fetched[0], session, sources.refresh_days, force))
    backlog = [c for c in due if c in fetched[0] and c not in fetched[1] and c not in shares_due]
    deferred = set(backlog[cap:])
    return [c for c in due if c not in deferred], len(deferred)


def ingest_shares(
    ctx: TaskContext,
    sources: SharesSources,
    session: date,
    force: bool = False,
    limit: int | None = None,
) -> RunRecord:
    ids = instrument_ciks(ctx.reader, session)
    light = {t.table: t.light(ctx.reader) for t in TARGETS}
    with IngestRun(ctx, TASK, session, resume=True) as run:
        ciks = sorted(set(ids["cik"]))
        fetched = [_fetched(light[t.table]) for t in TARGETS]
        priority = _prioritised(ctx, ids, session, ciks, sources.liquid_adv_usd)
        due, backlog_deferred = _due(ciks, fetched, session, sources, force, priority)
        todo = due if limit is None else due[: max(limit, 0)]
        members = dict(tuple(ids.groupby("cik")))
        todo_ids = list(ids["instrument_id"][ids["cik"].isin(todo)])
        known = {  # the stored keys of the instruments fetched now, not of the whole table
            t.table: {
                tuple(r)
                for r in t.keys(ctx.reader, todo_ids)[t.key].astype(object).itertuples(index=False)
            }
            if todo_ids
            else set()
            for t in TARGETS
        }
        for i, cik in enumerate(todo, start=1):
            if cik in run.items:
                continue  # fetched before a resume
            run.attempt(cik, partial(_fetch, run, sources.facts, cik, members[cik], known))
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        carried = {}
        for target in TARGETS:
            carried[target.table] = _carry(ctx.reader, target, light[target.table], ids, set(todo))
            if not carried[target.table].empty:
                frame = _typed(carried[target.table])
                run.stage(target.table, CARRY, frame, sources.facts.name)
        rows = {t.table: run.publish(t.table) for t in TARGETS}
        counts = run.counts()
        failed = run.failures()
        run.stats.update(
            instruments=len(ids),
            ciks=len(ciks),
            due=len(due) + backlog_deferred,
            requested=len(todo),
            with_facts=sum(n for s, n in counts.items() if s == "OK"),
            no_facts=counts.get("NO_FACTS", 0) + counts.get("NO_SHARE_FACTS", 0),
            deferred_by_limit=len(due) - len(todo) + backlog_deferred,
            carried=len(carried[TABLE]),
            statements_carried=len(carried[STATEMENTS]),
            failed=failed[:20],
            failed_count=len(failed),
            rows=rows[TABLE],
            statement_rows=rows[STATEMENTS],
        )
    return run.record
