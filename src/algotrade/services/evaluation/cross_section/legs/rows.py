"""A leg, a session's reads log and an outcome read as rows of ``results/edge_legs`` and back
(ADR 0063). The three row kinds share one table; a key column that does not apply is ``""`` (the
horizon 0), never null.

``encode_*`` give a row dict of declared column names, ``decode_*`` read one back from a dict or a
row of a frame read from the store (lists are arrays, nulls are None or NaN there). A leg round
trips exactly but for the random draws' sums (the uniform and, from leg v3, the sector-stratified
ones: ``strat_*``), stored as float32 (about 4 GB per edge otherwise):
the harness measures every leg through ``decode_leg(encode_leg(...))``, so a run that computes a
leg and a run that reads it hold the same numbers.

Leg v2 (ADR 0064 decision 4) stores every pick as ``pick_*`` lists aligned to ``pick_ids`` (a
value not known is a null element, never 0); a counted pick's value is not stored twice: the
counted picks (reason ``""``) are, in order, ``pick_values``. ``pick_flags`` packs a pick's
booleans (``HIT``, ``DELISTED``, ``TOUCH``; the touch is known when its reference is; ``SHORT``:
a name the leg is short, outcome sides). A ``long_short`` leg keeps its short names' counted values
in ``short_values`` (null for every other side, so a long leg's row is what it was), the long
leg's in ``pick_values``; a ``short`` leg's names are all short and their values ``pick_values``.

Leg v4 (ADR 0053 amendment 2026-10-18, buy/hold bands): an edge with ``[outcome] hold_rank`` also
keeps the names ranked just below its counted picks, ``top_k + 1`` to ``hold_rank``, as ``band_*``
lists (id, rank, oriented net value, null when the name has no counted value): the values the
turnover pass (``reporting/turnover.py``) needs for a name held through the band."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from algotrade.data import ReadRecord
from algotrade.data.listings.identity import PROXY, TODAY_FLAG
from algotrade.services.evaluation.cross_section.measures import UNCOUNTED_BAND, Pick, SessionStat
from algotrade.services.evaluation.cross_section.random_picks import RandomStat, SectorDraws

LEG = "leg"
READS = "reads"
OUTCOME = "outcome"
NO_KEY = ""  # a key column that does not apply to a row kind
IDENTITY = (("flag", TODAY_FLAG), ("proxy", PROXY))  # ``id_<kind>_<column>``: the paths
HIT, DELISTED, TOUCH, SHORT = 1, 2, 4, 8  # bits of ``pick_flags``


@dataclass(frozen=True)
class LegRecord:
    """One screener of one edge variant at one decision session and horizon (``stat.session``)."""

    key: str  # the leg key (``legs/key.py``)
    trial_hash: str
    edge_variant: str
    variant: str
    horizon: int
    entry: date  # the entry session S whose outcome partition was read
    stat: SessionStat
    outcomes_as_of: datetime  # the ``as_of`` the outcome read used
    random: RandomStat | None = None  # screeners from the split on
    event_ids: tuple[str, ...] | None = None  # sorted; None: no event schedule
    lost_table: str | None = None  # the table the screener had no data in at D
    snapshot: date | None = None  # the universe snapshot the screen read
    outcome_seq: int | None = None  # the outcome partition's commit sequence at the read
    known: datetime | None = None  # the row's ``knowledge_ts``, set when read from the store

    @property
    def day(self) -> date:
        return self.stat.session


@dataclass(frozen=True)
class DayReads:
    """What a decision session read: its ``ReadRecord``s, the store's commit sequence at its
    first read and the historical-identity counts per kind (eligible, screened) and path."""

    day: date
    reads: tuple[ReadRecord, ...]
    inputs_seq: int | None
    eligible: Mapping[str, int] = field(default_factory=dict)
    screened: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class OutcomeRead:
    """The outcome partition of entry session S a decision session D joined: ``as_of`` the read
    used and the partition's commit sequence (None: no partition)."""

    day: date
    edge_variant: str
    horizon: int
    entry: date
    as_of: datetime
    seq: int | None


@dataclass(frozen=True)
class StoredLegs:
    """Every row of one edge's partitions decoded: legs by (leg key, edge variant, screener,
    horizon, D), reads by D and outcome reads by (edge variant, horizon, D)."""

    legs: Mapping[tuple[str, str, str, int, date], LegRecord] = field(default_factory=dict)
    reads: Mapping[date, DayReads] = field(default_factory=dict)
    outcomes: Mapping[tuple[str, int, date], OutcomeRead] = field(default_factory=dict)


def _null(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _opt(value: Any) -> Any:
    return None if _null(value) else value


def _stored(value: Any) -> bool:
    """``siblings_stored`` of a row: a leg written before the column existed (null) is read as
    stored, so it claims no gap it never measured."""
    return True if _null(value) else bool(value)


def _int(value: Any) -> int | None:
    return None if _null(value) else int(value)


def _day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else pd.Timestamp(value).date()


def _opt_day(value: Any) -> date | None:
    return None if _null(value) else _day(value)


def _moment(value: Any) -> datetime:
    stamp = pd.Timestamp(value)
    return (stamp if stamp.tzinfo else stamp.tz_localize("UTC")).to_pydatetime()


def _list(value: Any) -> list[Any]:
    return [] if _null(value) else list(value)


def _floats(value: Any) -> tuple[float, ...]:
    return () if _null(value) else tuple(float(v) for v in value)


def _ints(value: Any) -> tuple[int, ...]:
    return () if _null(value) else tuple(int(v) for v in value)


def _maybe(value: Any) -> float | None:
    return None if _null(value) else float(value)


def _flags(pick: Pick) -> int:
    return (
        (HIT if pick.hit else 0)
        | (DELISTED if pick.delisted else 0)
        | (TOUCH if pick.touch else 0)
        | (SHORT if pick.side == "short" else 0)
    )


def encode_picks(picks: Sequence[Pick]) -> dict[str, list[Any]]:
    """A leg's picks as the ``pick_*`` list columns, aligned to ``pick_ids``."""
    return {
        "pick_ids": [p.instrument_id for p in picks],
        "pick_ranks": [p.rank for p in picks],
        "pick_reasons": [p.reason for p in picks],
        "pick_scores": [p.score for p in picks],
        "pick_gross": [p.gross for p in picks],
        "pick_mdd": [p.drawdown for p in picks],
        "pick_adv": [p.adv for p in picks],
        "pick_refs": [p.reference for p in picks],
        "pick_flags": [_flags(p) for p in picks],
    }


def decode_picks(
    row: Mapping[str, Any], values: Sequence[float], shorts: Sequence[float] | None = None
) -> tuple[Pick, ...]:
    """The picks of a leg row (none for a v1 row); ``values``: its ``pick_values``, the counted
    picks' in order (``shorts``: the ``short_values`` of a long-short row, which the counted short
    names take instead). A row whose counted picks do not match them is corrupt: ValueError."""
    ids = _list(row.get("pick_ids"))
    if not ids:
        return ()
    ranks, reasons = _list(row.get("pick_ranks")), _list(row.get("pick_reasons"))
    scores, gross, mdd = (_list(row.get(c)) for c in ("pick_scores", "pick_gross", "pick_mdd"))
    adv, refs, flags = (_list(row.get(c)) for c in ("pick_adv", "pick_refs", "pick_flags"))
    is_short = [bool(int(f) & SHORT) for f in flags]
    split = shorts is not None
    kept = [sh for r, sh in zip(reasons, is_short, strict=True) if r == ""]  # counted picks
    short_n = sum(kept) if split else 0
    long_n = len(kept) - short_n
    if long_n != len(values) or short_n != len(shorts or ()):
        raise ValueError(f"leg {row.get('leg_key')}: counted picks do not match pick_values")
    counted, counted_short = iter(values), iter(shorts or ())
    out = []
    for at, instrument in enumerate(ids):
        bits, reason, ref = int(flags[at]), str(reasons[at]), _maybe(refs[at])
        out.append(
            Pick(
                instrument_id=str(instrument),
                rank=int(ranks[at]),
                reason=reason,
                value=(next(counted_short) if split and is_short[at] else next(counted))
                if reason == ""
                else None,
                hit=bool(bits & HIT),
                delisted=bool(bits & DELISTED),
                score=_maybe(scores[at]),
                gross=_maybe(gross[at]),
                drawdown=_maybe(mdd[at]),
                adv=_maybe(adv[at]),
                reference=ref,
                touch=None if ref is None else bool(bits & TOUCH),
                side="short" if is_short[at] else "long",
            )
        )
    return tuple(out)


def encode_band(band: Sequence[Pick]) -> dict[str, list[Any] | None]:
    """A leg's buy/hold band (leg v4) as ``band_*`` lists aligned to ``band_ids``; null for a leg
    with none, so a leg of an edge without ``hold_rank`` carries nothing new. A name with no
    counted value has a null value, never 0."""
    if not band:
        return {"band_ids": None, "band_ranks": None, "band_values": None}
    return {
        "band_ids": [p.instrument_id for p in band],
        "band_ranks": [p.rank for p in band],
        "band_values": [p.value for p in band],
    }


def decode_band(row: Mapping[str, Any]) -> tuple[Pick, ...]:
    """The band of a leg row (none for a row without one, or from before leg v4)."""
    ids, ranks, values = (_list(row.get(c)) for c in ("band_ids", "band_ranks", "band_values"))
    return tuple(
        Pick(str(i), int(r), "" if not _null(v) else UNCOUNTED_BAND, value=_maybe(v))
        for i, r, v in zip(ids, ranks, values, strict=True)
    )


def _base(
    kind: str,
    user_id: str,
    edge_id: str,
    day: date,
    key: str,
    edge_variant: str,
    variant: str,
    horizon: int,
) -> dict[str, Any]:
    return {
        "user_id": user_id, "edge_id": edge_id, "row_kind": kind, "leg_key": key,
        "edge_variant": edge_variant, "variant": variant, "horizon_sessions": horizon,
        "session_date": day,
    }  # fmt: skip


def encode_leg(record: LegRecord, user_id: str, edge_id: str) -> dict[str, Any]:
    s, r = record.stat, record.random
    row = _base(
        LEG, user_id, edge_id, s.session, record.key, record.edge_variant, record.variant,
        record.horizon,
    )  # fmt: skip
    row.update(
        trial_hash=record.trial_hash,
        entry_session=record.entry,
        outcomes_as_of=record.outcomes_as_of,
        screen_snapshot=record.snapshot,
        outcome_seq=record.outcome_seq,
        lost_table=record.lost_table,
        event_ids=None if record.event_ids is None else list(record.event_ids),
        regime=s.regime,
        pick_values=list(s.pick_values),
        pick_hits=s.pick_hits,
        rest_n=s.rest[0],
        rest_mean=s.rest[1],
        rest_m2=s.rest[2],
        base_hits=s.base_hits,
        top_decile=s.top_decile,
        spread=s.spread,
        deciles=list(s.deciles),
        ranked=s.ranked,
        unscored=s.unscored,
        excluded_score_coverage=s.excluded_score_coverage,
        excluded_unclosed=s.excluded_unclosed,
        excluded_missing=s.excluded_missing,
        excluded_coverage=s.excluded_coverage,
        excluded_unmeasured=s.excluded_unmeasured,
        unmeasured_base=s.unmeasured_base,
        delisted=s.delisted,
        pre_snapshot=s.pre_snapshot,
        outside_universe=s.outside_universe,
        no_entry_bar=s.no_entry_bar,
        pick_reference=list(s.pick_reference),
        pick_touches=s.pick_touches,
        no_implied_vol=s.no_implied_vol,
        implied_stored=s.implied_stored,
        siblings_stored=s.siblings_stored,
        base_hits_at=list(s.base_hits_at),
        pick_hits_at=list(s.pick_hits_at),
        short_values=None if s.short_values is None else list(s.short_values),
        **encode_picks(s.picks),
        **encode_band(s.band),
    )
    if r is not None:
        row.update(
            rand_picks=r.picks,
            rand_eligible=r.eligible,
            rand_base_hits=r.base_hits,
            value_sums=np.asarray(r.value_sums, dtype=np.float32),
            hit_sums=np.asarray(r.hit_sums, dtype=np.float32),
        )
        if r.sector is not None:  # leg v3: the sector-stratified draws beside the uniform ones
            row.update(
                strat_picks=r.sector.picks,
                strat_value_sums=np.asarray(r.sector.value_sums, dtype=np.float32),
                strat_hit_sums=np.asarray(r.sector.hit_sums, dtype=np.float32),
            )
    return row


def encode_tombstone(record: LegRecord, user_id: str, edge_id: str) -> dict[str, Any]:
    """The row that replaces ``record`` under its key and says it is gone: a leg of a trial the
    edge no longer has, or one the run did not compute again at a session it rewrote."""
    row = _base(
        LEG, user_id, edge_id, record.day, record.key, record.edge_variant, record.variant,
        record.horizon,
    )  # fmt: skip
    return {**row, "tombstone": True}


def decode_leg(row: Mapping[str, Any]) -> LegRecord:
    """The leg of a ``leg`` row (a dict ``encode_leg`` made, or a row of the stored frame)."""
    day = _day(row["session_date"])
    rand = _int(row.get("rand_picks"))
    events: Any = row.get("event_ids")
    values = _floats(row.get("pick_values"))
    shorts = None if _null(row.get("short_values")) else _floats(row.get("short_values"))
    stat = SessionStat(
        session=day,
        regime=str(row["regime"]),
        pick_values=values,
        pick_hits=int(row["pick_hits"]),
        rest=(int(row["rest_n"]), float(row["rest_mean"]), float(row["rest_m2"])),
        base_hits=int(row["base_hits"]),
        top_decile=_opt(row.get("top_decile")),
        spread=_opt(row.get("spread")),
        deciles=_floats(row.get("deciles")),
        ranked=int(row["ranked"]),
        unscored=int(row["unscored"]),
        excluded_score_coverage=int(row["excluded_score_coverage"]),
        excluded_unclosed=int(row["excluded_unclosed"]),
        excluded_missing=int(row["excluded_missing"]),
        excluded_coverage=int(row["excluded_coverage"]),
        excluded_unmeasured=int(row["excluded_unmeasured"]),
        unmeasured_base=int(row["unmeasured_base"]),
        delisted=int(row["delisted"]),
        pre_snapshot=bool(row["pre_snapshot"]),
        outside_universe=int(row["outside_universe"]),
        no_entry_bar=int(row["no_entry_bar"]),
        pick_reference=_floats(row.get("pick_reference")),
        pick_touches=int(row["pick_touches"]),
        no_implied_vol=int(row["no_implied_vol"]),
        implied_stored=bool(row["implied_stored"]),
        siblings_stored=_stored(row.get("siblings_stored")),
        picks=decode_picks(row, values, shorts),
        band=decode_band(row),
        base_hits_at=_ints(row.get("base_hits_at")),
        pick_hits_at=_ints(row.get("pick_hits_at")),
        short_values=shorts,
    )
    drawn = None
    if rand is not None:
        drawn = RandomStat(
            session=day,
            picks=rand,
            value_sums=np.asarray(row["value_sums"], dtype=np.float64),
            hit_sums=np.asarray(row["hit_sums"], dtype=np.float64),
            eligible=int(row["rand_eligible"]),
            base_hits=int(row["rand_base_hits"]),
            sector=_sector_draws(row),
        )
    return LegRecord(
        key=str(row["leg_key"]),
        trial_hash=str(row["trial_hash"]),
        edge_variant=str(row["edge_variant"]),
        variant=str(row["variant"]),
        horizon=int(row["horizon_sessions"]),
        entry=_day(row["entry_session"]),
        stat=stat,
        outcomes_as_of=_moment(row["outcomes_as_of"]),
        random=drawn,
        event_ids=None if _null(events) else tuple(str(i) for i in events),
        lost_table=_opt(row.get("lost_table")),
        snapshot=_opt_day(row.get("screen_snapshot")),
        outcome_seq=_int(row.get("outcome_seq")),
        known=None if _null(row.get("knowledge_ts")) else _moment(row["knowledge_ts"]),
    )


def _sector_draws(row: Mapping[str, Any]) -> SectorDraws | None:
    """The stratified draws of a leg row (None: a row from before leg v3, or not drawn)."""
    picks = _int(row.get("strat_picks"))
    if picks is None:
        return None
    return SectorDraws(
        picks,
        np.asarray(row["strat_value_sums"], dtype=np.float64),
        np.asarray(row["strat_hit_sums"], dtype=np.float64),
    )


def encode_reads(reads: DayReads, user_id: str, edge_id: str) -> dict[str, Any]:
    row = _base(READS, user_id, edge_id, reads.day, NO_KEY, NO_KEY, NO_KEY, 0)
    row.update(
        inputs_seq=reads.inputs_seq,
        read_table=[r.table for r in reads.reads],
        read_kind=[r.kind for r in reads.reads],
        read_digest=[r.digest or "" for r in reads.reads],
        read_from=[r.start for r in reads.reads],
        read_to=[r.end for r in reads.reads],
    )
    for kind, counts in (("eligible", reads.eligible), ("screened", reads.screened)):
        for column, path in IDENTITY:
            row[f"id_{kind}_{column}"] = counts.get(path)
    return row


def decode_reads(row: Mapping[str, Any]) -> DayReads:
    tables, kinds, digests = (_list(row.get(c)) for c in ("read_table", "read_kind", "read_digest"))
    starts, ends = _list(row.get("read_from")), _list(row.get("read_to"))
    records = tuple(
        ReadRecord(str(t), _day(a), _day(b), str(k), str(d) or None)
        for t, k, d, a, b in zip(tables, kinds, digests, starts, ends, strict=True)
    )

    def counts(kind: str) -> dict[str, int]:
        found = {path: _int(row.get(f"id_{kind}_{column}")) for column, path in IDENTITY}
        return {path: n for path, n in found.items() if n is not None}

    return DayReads(
        _day(row["session_date"]),
        records,
        _int(row.get("inputs_seq")),
        counts("eligible"),
        counts("screened"),
    )


def encode_outcome(read: OutcomeRead, user_id: str, edge_id: str) -> dict[str, Any]:
    row = _base(
        OUTCOME, user_id, edge_id, read.day, NO_KEY, read.edge_variant, NO_KEY, read.horizon
    )
    row.update(entry_session=read.entry, outcomes_as_of=read.as_of, outcome_seq=read.seq)
    return row


def decode_outcome(row: Mapping[str, Any]) -> OutcomeRead:
    return OutcomeRead(
        _day(row["session_date"]),
        str(row["edge_variant"]),
        int(row["horizon_sessions"]),
        _day(row["entry_session"]),
        _moment(row["outcomes_as_of"]),
        _int(row.get("outcome_seq")),
    )


def decode_frame(frame: pd.DataFrame | None) -> StoredLegs:
    """Every row of a frame read from ``results/edge_legs`` (one edge's), by kind."""
    legs: dict[tuple[str, str, str, int, date], LegRecord] = {}
    reads: dict[date, DayReads] = {}
    outcomes: dict[tuple[str, int, date], OutcomeRead] = {}
    if frame is None or frame.empty:
        return StoredLegs(legs, reads, outcomes)
    for record in frame.to_dict("records"):
        row = {str(k): v for k, v in record.items()}
        kind = row["row_kind"]
        if kind == LEG and not _null(row.get("tombstone")) and bool(row["tombstone"]):
            continue  # the latest row of its key says the leg is gone
        if kind == LEG:
            leg = decode_leg(row)
            legs[leg.key, leg.edge_variant, leg.variant, leg.horizon, leg.day] = leg
        elif kind == READS:
            found = decode_reads(row)
            reads[found.day] = found
        elif kind == OUTCOME:
            seen = decode_outcome(row)
            outcomes[seen.edge_variant, seen.horizon, seen.day] = seen
    return StoredLegs(legs, reads, outcomes)
