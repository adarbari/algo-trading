"""``bar-quality``: flag the stored daily bars that cannot be right (ADR 0061).

Writes ``events/bar_flag``.

Raw bars are never edited (ADR 0007): a bar that is wrong is flagged, and ``data.prices`` drops
flagged bars at read time as it applies splits. ``bad_bars`` is the pure detector; the task
reads the stored bars of a range, writes the changes, and FAILS when over
``[quality] max_bad_bar_share`` of the bars read are flagged (a detector gone wrong, not data:
nothing is published).

A bar is flagged when:

- ``BELOW_FLOOR``: its close is below ``min_bar_close`` (or not positive);
- ``BAD_OHLC``: its high is below its low, or its close is outside low..high;
- ``UNEXPLAINED_JUMP``: it is in a segment of its series that is not the trusted one. The close
  ratio of two consecutive bars above ``max_bar_jump`` (either way) cuts the series, unless a
  split event of the instrument is within ``split_window_sessions`` bars of the jump (a real
  split or reverse split is explained). A one-bar spike that returns to its level is flagged
  alone; the series around it stays one segment. Of the segments, the trusted one holds the most
  ``source = "massive"`` bars (the vendor whose history we trust), none: the one holding the
  latest bar; a tie goes to the later segment. Every other segment is flagged.

Zero volume is not flagged. A bar flagged for two reasons keeps the first in the order above.
Rows: ``instrument_id``, ``ts`` (the bar's close), ``reason``, ``detail``, ``status``
(``FLAGGED``, or ``CLEARED`` for a bar flagged earlier that is fine now: the table keeps the
latest row per (instrument, ts)). A rerun writes only what changed. Without ``--from`` the task
reads the trailing ``TRAILING_SESSIONS`` sessions (the nightly step, after ``bars`` and
``corporate-actions``, which explain real splits): an ``UNEXPLAINED_JUMP`` flag clears only when
a run starts at the instrument's first bar, so the nightly never retracts one. The range limits the
read: segments are judged within it (the full history for a rebuild).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.data.events import read_events
from algotrade.data.prices import FLAGGED, FLAGS_TABLE, raw_bars
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "bar_quality"
CLEARED = "CLEARED"
BELOW_FLOOR, BAD_OHLC, UNEXPLAINED_JUMP = "BELOW_FLOOR", "BAD_OHLC", "UNEXPLAINED_JUMP"
TRUSTED_SOURCE = "massive"
TRAILING_SESSIONS = 60  # the nightly step reads this many sessions ending on its own
PIECE = 60  # sessions read at a time: each piece is kept compact before the next is read
FLAG_COLUMNS = ["instrument_id", "ts", "reason", "detail"]
_NO_FLAGS = pd.DataFrame(columns=FLAG_COLUMNS)


def _ns(values: pd.Series) -> np.ndarray:
    return pd.to_datetime(values, utc=True).dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")


def _unexplained(jumps: np.ndarray, ex_dates: np.ndarray, ts: np.ndarray, window: int) -> list[int]:
    """The jump positions (first bar after the jump) of one series that no split explains."""
    if not len(ex_dates):
        return [int(j) for j in jumps]
    at = np.searchsorted(ts, ex_dates, side="left")  # first bar on or after each ex-date
    return [int(j) for j in jumps if not np.any(np.abs(at - j) <= window)]


def split_like(ratio: float) -> int | None:
    """The integer ``n`` in 2..50 a jump ratio (either way) is within 2% of, else None: a jump
    that looks like a split nobody recorded."""
    r = max(ratio, 1 / ratio) if ratio > 0 else 0.0
    n = round(r)
    return n if 2 <= n <= 50 and abs(r / n - 1) <= 0.02 else None


def _tag(close: np.ndarray, cuts: list[int], lo: int, hi: int) -> str:
    """``; split_like=n`` when the largest jump bounding ``lo..hi`` looks like a split."""
    edges = [c for c in (lo, hi) if 0 < c < len(close) and close[c] > 0 and close[c - 1] > 0]
    if not edges:
        return ""
    edge = max(edges, key=lambda c: abs(np.log(close[c] / close[c - 1])))
    n = split_like(float(close[edge] / close[edge - 1]))
    return f"; split_like={n}" if n else ""


def _series_flags(
    close: np.ndarray,
    ts: np.ndarray,
    massive: np.ndarray,
    cuts: list[int],
    max_jump: float,
) -> tuple[np.ndarray, str]:
    """Positions of one series to flag as ``UNEXPLAINED_JUMP`` and the detail's text: one-bar
    spikes alone, then every segment but the trusted one."""
    spikes: list[int] = []
    kept: list[int] = []
    i = 0
    while i < len(cuts):
        c = cuts[i]
        back = close[c - 1] if c >= 1 else 0.0
        if (
            i + 1 < len(cuts)
            and cuts[i + 1] == c + 1
            and back > 0
            and 1 / max_jump <= close[c + 1] / back <= max_jump
        ):
            spikes.append(c)  # up and straight back: only this bar is wrong
            i += 2
            continue
        kept.append(c)
        i += 1
    flagged = list(spikes)
    detail = f"one-bar spike beyond {max_jump:g}x with no split event nearby"
    if spikes:
        detail += _tag(close, cuts, spikes[0], spikes[0] + 1)
    if kept:
        bounds = [0, *kept, len(close)]
        segments = list(pairwise(bounds))
        counts = [int(massive[a:b].sum()) for a, b in segments]
        best = max(counts)
        trusted = (
            max(i for i, n in enumerate(counts) if n == best) if best > 0 else len(segments) - 1
        )
        a, b = segments[trusted]
        for i, (lo, hi) in enumerate(segments):
            if i != trusted:
                flagged.extend(range(lo, hi))
        first, last = pd.Timestamp(ts[a]).date(), pd.Timestamp(ts[b - 1]).date()
        detail = (
            f"outside the trusted segment {first}..{last}"
            f" (closes cut by a jump beyond {max_jump:g}x with no split event nearby)"
        )
        detail += _tag(close, kept, a, b)
    return np.array(sorted(set(flagged)), dtype=int), detail


def bad_bars(bars: pd.DataFrame, splits: pd.DataFrame, s: SourcesSettings) -> pd.DataFrame:
    """The flagged bars of ``bars`` (``instrument_id``, ``ts``, ``high``, ``low``, ``close``,
    ``source``; any order) as ``FLAG_COLUMNS`` rows, sorted by (instrument_id, ts); ``splits``
    (``instrument_id``, ``ts``) explain jumps (module doc)."""
    if bars.empty:
        return _NO_FLAGS.copy()
    ids = pd.Categorical(bars["instrument_id"].astype(str))
    ts_all = _ns(bars["ts"])
    order = np.lexsort((ts_all, ids.codes))
    codes = ids.codes[order]
    ts = ts_all[order]
    close = bars["close"].to_numpy(dtype=float)[order]
    high = bars["high"].to_numpy(dtype=float)[order]
    low = bars["low"].to_numpy(dtype=float)[order]
    massive = (bars["source"].astype(str).to_numpy() == TRUSTED_SOURCE)[order]
    reason = np.full(len(close), "", dtype=object)
    detail = np.full(len(close), "", dtype=object)

    ohlc = (high < low) | (close > high) | (close < low)
    reason[ohlc], detail[ohlc] = BAD_OHLC, "high below low, or close outside low..high"
    floor = ~(close >= s.min_bar_close)  # below the floor, not positive (NaN is not flagged)
    floor &= ~np.isnan(close)
    reason[floor] = BELOW_FLOOR
    detail[floor] = [f"close {c:.6g} below {s.min_bar_close:g}" for c in close[floor]]

    same = codes[1:] == codes[:-1]
    both = same & (close[:-1] > 0) & (close[1:] > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = close[1:] / close[:-1]
    jump = both & ((ratio > s.max_bar_jump) | (ratio < 1 / s.max_bar_jump))
    where = np.flatnonzero(jump) + 1
    if len(where):
        split_ids: np.ndarray = (
            splits["instrument_id"].astype(str).to_numpy()
            if len(splits)
            else np.array([], dtype=str)
        )
        split_ts = _ns(splits["ts"]) if len(splits) else np.array([], dtype="datetime64[ns]")
        names = ids.categories
        for code in np.unique(codes[where]):
            lo, hi = np.searchsorted(codes, [code, code + 1])
            mine = where[(where >= lo) & (where < hi)] - lo
            ex = split_ts[np.asarray(split_ids == names[code])] if len(split_ids) else split_ts
            cuts = _unexplained(mine, ex, ts[lo:hi], s.split_window_sessions)
            if not cuts:
                continue
            positions, text = _series_flags(
                close[lo:hi], ts[lo:hi], massive[lo:hi], cuts, s.max_bar_jump
            )
            for p in positions:
                if not reason[lo + p]:
                    reason[lo + p], detail[lo + p] = UNEXPLAINED_JUMP, text
    keep = reason != ""
    out = pd.DataFrame(
        {
            "instrument_id": np.asarray(ids.categories[codes[keep]], dtype=object),
            "ts": pd.to_datetime(ts[keep], utc=True),
            "reason": reason[keep],
            "detail": detail[keep],
        }
    )
    return out.reset_index(drop=True)


def compact(frame: pd.DataFrame) -> pd.DataFrame:
    """Bars (``instrument_id``, ``ts``, ``high``, ``low``, ``close``, ``source``) as ``bad_bars``
    reads them: categorical id and source, four numbers a row."""
    return pd.DataFrame(
        {
            "instrument_id": pd.Categorical(frame["instrument_id"].astype(str)),
            "ts": pd.to_datetime(frame["ts"], utc=True),
            "high": frame["high"].to_numpy(dtype=float),
            "low": frame["low"].to_numpy(dtype=float),
            "close": frame["close"].to_numpy(dtype=float),
            "source": pd.Categorical(frame["source"].astype(str)),
        }
    )


def read_compact(
    ctx: TaskContext, start: date, end: date, instruments: list[str] | None
) -> pd.DataFrame:
    """The stored bars of ``start..end`` as ``bad_bars`` reads them, read ``PIECE`` sessions at a
    time and kept compact (categorical id and source, four numbers a row): years of every
    instrument are a few hundred MB, not the GB of the full bars."""
    pieces: list[pd.DataFrame] = []
    days = sessions_between(start, end)
    for i in range(0, len(days), PIECE):
        part = days[i : i + PIECE]
        try:
            columns = ("high", "low", "close")
            frame = raw_bars(ctx.reader, "1d", part[0], part[-1], instruments, None, columns)
        except MissingDataError:
            continue
        pieces.append(compact(frame))
    if not pieces:
        return pd.DataFrame(columns=["instrument_id", "ts", "high", "low", "close", "source"])
    return pd.concat(_unified(pieces), ignore_index=True)


def _unified(pieces: list[pd.DataFrame]) -> list[pd.DataFrame]:
    """``pieces`` with one category set per categorical column (``concat`` would go to object)."""
    for column in ("instrument_id", "source"):
        merged = union_categoricals([p[column] for p in pieces], sort_categories=False)
        for p in pieces:
            p[column] = pd.Categorical(p[column].astype(str), categories=merged.categories)
    return pieces


def changes(
    found: pd.DataFrame, stored: pd.DataFrame, protected: frozenset[str] = frozenset()
) -> pd.DataFrame:
    """The rows to write: each found flag that is not already ``FLAGGED`` for its reason, and a
    ``CLEARED`` row for every stored ``FLAGGED`` bar that is not found any more. An
    ``UNEXPLAINED_JUMP`` flag is judged against the whole series: it is cleared only for an
    instrument whose series the read started at (``protected``: instruments with stored bars
    before the range keep theirs, the jump may lie outside it)."""
    key = ["instrument_id", "ts"]
    held = stored[stored["status"] == FLAGGED] if len(stored) else stored
    held = held.reindex(columns=[*key, "reason"]).assign(
        ts=lambda f: pd.to_datetime(f["ts"], utc=True)
    )
    new = found.assign(status=FLAGGED).merge(held, on=key, how="left", suffixes=("", "_held"))
    new = new[new["reason_held"].isna() | (new["reason_held"] != new["reason"])]
    gone = held.merge(found[key], on=key, how="left", indicator=True)
    gone = gone[gone["_merge"] == "left_only"]
    keep = (gone["reason"] == UNEXPLAINED_JUMP) & gone["instrument_id"].astype(str).isin(protected)
    gone = gone[~keep].assign(
        reason=lambda f: f["reason"], detail="no longer flagged", status=CLEARED
    )
    columns = [*FLAG_COLUMNS, "status"]
    return pd.concat([new[columns], gone[columns]], ignore_index=True)


def _with_earlier_bars(
    ctx: TaskContext, stored: pd.DataFrame, start: date, instruments: list[str] | None
) -> frozenset[str]:
    """The instruments with a stored ``UNEXPLAINED_JUMP`` flag that have bars before ``start``."""
    if not len(stored):
        return frozenset()
    jumped = stored[(stored["status"] == FLAGGED) & (stored["reason"] == UNEXPLAINED_JUMP)]
    ids = sorted(set(jumped["instrument_id"].astype(str)))
    if not ids:
        return frozenset()
    dates = ctx.reader.dates("bars/1d")
    if not dates or dates[0] >= start:
        return frozenset()
    try:
        earlier = raw_bars(
            ctx.reader, "1d", dates[0], start - timedelta(days=1), ids, None, ("close",)
        )
    except MissingDataError:
        return frozenset()
    return frozenset(earlier["instrument_id"].astype(str))


@dataclass(frozen=True)
class FlagPlan:
    """What a read of ``start..end`` found: the bars read, the flags found, the rows to write."""

    bars: int
    found: pd.DataFrame
    write: pd.DataFrame


def plan_flags(
    ctx: TaskContext,
    start: date,
    end: date,
    instruments: list[str] | None,
    added_bars: pd.DataFrame | None = None,
    added_splits: pd.DataFrame | None = None,
) -> FlagPlan:
    """Read the stored bars and splits of ``start..end`` and decide the flag rows to write.
    ``added_bars`` / ``added_splits``: rows a running task is about to publish (``read_compact``
    columns; ``instrument_id``, ``ts``), judged as if stored, so its flags can be published with
    them (``bars-history``)."""
    s = ctx.settings
    bars = read_compact(ctx, start, end, instruments)
    if added_bars is not None and len(added_bars):
        both = [added_bars.copy()] if bars.empty else [bars, added_bars.copy()]
        bars = pd.concat(_unified(both), ignore_index=True)
    day = timedelta(days=1)
    window = timedelta(days=30)  # calendar slack for split_window_sessions
    splits = read_events(ctx.reader, "events/split", start - window, end + window, instruments)
    frame = splits.frame
    if added_splits is not None and len(added_splits):
        keep = ["instrument_id", "ts"]
        frame = pd.concat([frame[keep] if len(frame) else frame, added_splits[keep]])
    found = bad_bars(bars, frame, s)
    stored = read_events(ctx.reader, FLAGS_TABLE, start - day, end + day, instruments).frame
    if len(stored) and len(bars):
        seen = set(bars["instrument_id"].astype(str).unique())
        first, last = bars["ts"].min(), bars["ts"].max()
        inside = stored["instrument_id"].astype(str).isin(seen)
        when = pd.to_datetime(stored["ts"], utc=True)
        stored = stored[inside & (when >= first) & (when <= last)]
    protected = _with_earlier_bars(ctx, stored, start, instruments)
    return FlagPlan(len(bars), found, changes(found, stored, protected))


def flag_stats(plan: FlagPlan) -> dict[str, object]:
    """The run stats every flag-writing task reports."""
    found, write = plan.found, plan.write
    return {
        "bars": plan.bars,
        "flagged": len(found),
        "flagged_share": round(len(found) / max(plan.bars, 1), 6),
        "by_reason": {k: int(v) for k, v in found["reason"].value_counts().items()},
        "instruments_flagged": int(found["instrument_id"].nunique()),
        "split_like_ids": sorted(
            found.loc[found["detail"].str.contains("split_like="), "instrument_id"].unique()
        ),
        "written": len(write),
        "cleared": int((write["status"] == CLEARED).sum()),
    }


def run_bar_quality(
    ctx: TaskContext,
    session: date,
    start: date,
    end: date | None = None,
    instruments: list[str] | None = None,
) -> RunRecord:
    """Flag the bars of ``start..end`` (default: the session) and write what changed."""
    end = end or session
    s = ctx.settings
    with IngestRun(ctx, TASK, session) as run:
        plan = plan_flags(ctx, start, end, instruments)
        run.stats.update(window=[start.isoformat(), end.isoformat()], **flag_stats(plan))
        share = len(plan.found) / max(plan.bars, 1)
        if share > s.max_bad_bar_share:
            run.failed(
                f"{len(plan.found)} of {plan.bars} bars flagged ({share:.2%}, max "
                f"{s.max_bad_bar_share:.2%}): check the detector before trusting the flags"
            )
        elif len(plan.write):
            run.write(FLAGS_TABLE, plan.write, TASK)
    return run.record


def suspect_instruments(
    reader: StoreReader, ids: Sequence[str], start: date, end: date, s: SourcesSettings
) -> list[str]:
    """The ``ids`` whose stored bars over ``start..end`` hold a bar the detector flags (flagged
    already or not): a return over it is a bad datum, not a squeeze (``outcomes``' acceptance)."""
    bars = compact(raw_bars(reader, "1d", start, end, list(ids), None, ("high", "low", "close")))
    day = timedelta(days=30)  # slack for the split window
    splits = read_events(reader, "events/split", start - day, end + day, list(ids)).frame
    return sorted(set(bad_bars(bars, splits, s)["instrument_id"].astype(str)))
