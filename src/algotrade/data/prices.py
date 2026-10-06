"""Bars: read stored (unadjusted) bars and turn them into the aligned ``PriceSeries`` engines use.

Corporate actions are applied here, at read time (ADR 0016), from ``events/split`` and
``events/dividend`` read by event date (``data.events``):

- ``none``:         prices as traded
- ``splits``:       earlier bars divided by each later split ratio (volume multiplied), so a
                    split is not a price jump; the default for backtests
- ``total_return``: splits, plus earlier bars scaled by ``1 - dividend / previous close`` at
                    each ex-date, so returns include dividends

``session_bars`` serves rollups: one load for a range of sessions, then each session's
lookback window split-adjusted as of that session (never by a later split).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.model.fields import REFERENCE_TABLE
from algotrade.core.model.instruments import Instrument
from algotrade.core.time.calendar import sessions_between
from algotrade.core.views.series import FIELDS, PriceSeries, align
from algotrade.data.events import read_events
from algotrade.data.reference import REFERENCE_HINT, Snapshot, instrument_terms, read_snapshot
from algotrade.storage.tables.readers import StoreReader


def bars(
    reader: StoreReader,
    interval: str,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Bars for ``start <= session_date <= end``, sorted by (instrument_id, ts). ``columns``:
    only these (and the key and point-in-time columns) are read: a long window of one price.

    Raises ``MissingDataError`` when nothing is stored; backtests never fetch (ADR 0008).
    """
    table = f"bars/{interval}"
    frame = reader.table_range(table, start, end, as_of, instruments, columns)
    if frame is None:
        hint = f"run the ingestion job that loads {table} for {start}..{end}"
        raise MissingDataError(table, f"no bars between {start} and {end}", hint)
    return frame.sort_values(["instrument_id", "ts"], kind="stable").reset_index(drop=True)


def frame_to_series(bars: pd.DataFrame) -> dict[str, PriceSeries]:
    """Split a bars frame (sorted by instrument, ts) into one series per instrument."""
    out: dict[str, PriceSeries] = {}
    for instrument, rows in bars.groupby("instrument_id", sort=True):
        ts = pd.to_datetime(rows["ts"], utc=True).dt.tz_localize(None)
        out[str(instrument)] = PriceSeries(
            instrument_id=str(instrument),
            timestamps=ts.to_numpy(dtype="datetime64[ns]").copy(),
            **{f: rows[f].to_numpy(dtype=np.float64).copy() for f in FIELDS},
        )
    return out


ADJUSTMENTS = ("none", "splits", "total_return")
_PRICES = ["open", "high", "low", "close"]


def _utc_ns(values: pd.Series) -> np.ndarray:
    """Timestamps as naive UTC ``datetime64[ns]`` (fast comparisons, no Timestamp objects)."""
    return pd.to_datetime(values, utc=True).dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")


def _rows_of(ids: pd.Series, wanted: Sequence[str]) -> dict[str, np.ndarray]:
    """Row positions (ascending) of each wanted instrument; hashing, not a scan per event."""
    selected = np.flatnonzero(ids.isin(list(wanted)).to_numpy())
    sub = ids.to_numpy(dtype=str)[selected]
    return {iid: selected[sub == iid] for iid in set(wanted)}


def adjust_bars(
    bars: pd.DataFrame, splits: pd.DataFrame, dividends: pd.DataFrame, mode: str
) -> pd.DataFrame:
    """Back-adjust bars (sorted by instrument, ts) for corporate actions after each bar."""
    if mode not in ADJUSTMENTS:
        raise ConfigurationError(f"price adjustment must be one of {ADJUSTMENTS}, got {mode!r}")
    if mode == "none" or bars.empty:
        return bars
    out = bars.copy()
    ids = out["instrument_id"].astype(str)
    ts = _utc_ns(out["ts"])
    close = out["close"].to_numpy(dtype=float).copy()
    price_factor = np.ones(len(out))
    volume_factor = np.ones(len(out))
    if not splits.empty:
        split_ids = splits["instrument_id"].to_numpy(dtype=str)
        rows = _rows_of(ids, list(split_ids))
        for iid, when, ratio in zip(
            split_ids, _utc_ns(splits["ts"]), splits["ratio"].to_numpy(dtype=float), strict=True
        ):
            before = rows[iid][ts[rows[iid]] < when]
            price_factor[before] /= ratio
            volume_factor[before] *= ratio
    if mode == "total_return" and not dividends.empty:
        div_ids = dividends["instrument_id"].to_numpy(dtype=str)
        rows = _rows_of(ids, list(div_ids))
        amounts = dividends["cash_amount"].to_numpy(dtype=float)
        for iid, when, amount in zip(div_ids, _utc_ns(dividends["ts"]), amounts, strict=True):
            before = rows[iid][ts[rows[iid]] < when]
            if len(before):
                previous_close = close[before][-1]  # unadjusted basis, as the cash amount is
                if previous_close > amount:
                    price_factor[before] *= 1 - amount / previous_close
    prices = [c for c in _PRICES if c in out.columns]  # a column-pruned read has fewer
    out[prices] = out[prices].to_numpy() * price_factor[:, None]
    if "volume" in out.columns:
        out["volume"] = out["volume"].to_numpy() * volume_factor
    return out


def adjusted_bars(
    reader: StoreReader,
    interval: str,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
    adjustment: str = "splits",
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """``bars`` adjusted for the splits (and dividends) whose event date is in
    ``start..end`` (``adjust_bars``) -> (frame, table -> run ids read)."""
    if adjustment not in ADJUSTMENTS:
        raise ConfigurationError(
            f"price adjustment must be one of {ADJUSTMENTS}, got {adjustment!r}"
        )
    frame = bars(reader, interval, start, end, instruments, as_of)
    versions = {f"bars/{interval}": sorted(map(str, frame["run_id"].unique()))}
    if adjustment != "none":
        splits = read_events(reader, "events/split", start, end, instruments, as_of)
        dividends = read_events(reader, "events/dividend", start, end, instruments, as_of)
        frame = adjust_bars(frame, splits.frame, dividends.frame, adjustment)
        versions.update(
            {
                k: e.runs
                for k, e in (("events/split", splits), ("events/dividend", dividends))
                if e.runs
            }
        )
    return frame, versions


@dataclass(frozen=True)
class PriceData:
    """Aligned series, contract terms, and exactly which stored runs they came from."""

    series: dict[str, PriceSeries]
    terms: dict[str, Instrument]
    versions: dict[str, list[str]]  # table -> run ids read (for reproducibility)
    reference: Snapshot  # the reference snapshot used; pre_snapshot = survivorship bias


def load_price_data(
    reader: StoreReader,
    instruments: Sequence[str],
    start: date,
    end: date,
    interval: str = "1d",
    as_of: datetime | None = None,
    adjustment: str = "splits",
    aligned: bool = True,
) -> PriceData:
    """Aligned, corporate-action-adjusted series plus contract terms (as of ``start``).

    Splits and dividends are those whose event date falls in ``start..end``, wherever
    they were stored (``data.events``). ``aligned=False`` keeps each instrument's own bars
    (for a changing selection, which puts them on one timeline with ``core.views.series.panel``).
    """
    frame, versions = adjusted_bars(reader, interval, start, end, instruments, as_of, adjustment)
    reference, snapshot = read_snapshot(
        reader, REFERENCE_TABLE, start, REFERENCE_HINT, as_of, instruments
    )
    versions[REFERENCE_TABLE] = sorted(map(str, reference["run_id"].unique()))
    terms = instrument_terms(reader, start, instruments, as_of)
    series = frame_to_series(frame)
    return PriceData(align(series) if aligned else series, terms, versions, snapshot)


# ---------------------------------------------------------------------- per-session windows
_WINDOW_COLUMNS = ["instrument_id", "session_date", "open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class SessionBars:
    """Daily bars for a range of sessions, split-adjusted ONCE (to the range end), that hand
    out any session's lookback window in that session's share terms.

    A bar's split-adjusted price as of session D is its raw price divided by the ratios of the
    splits with ex-date in (bar, D]. The frame is adjusted for every split up to the range end,
    so ``window`` multiplies back the ratios of the splits after D: a later split never leaks
    into an earlier session's values (point in time), and one load serves a whole backfill.
    """

    frame: pd.DataFrame  # _WINDOW_COLUMNS, sorted by (session_date, instrument_id)
    splits: pd.DataFrame  # instrument_id, ex_date (date), ratio
    _days: np.ndarray  # frame session dates as datetime64[D], for slicing
    _rows: dict[str, np.ndarray]  # frame row positions of each instrument with a split

    @classmethod
    def empty(cls) -> "SessionBars":
        """No bars (a narrowed read whose instruments have none in the range)."""
        splits = pd.DataFrame({"instrument_id": [], "ex_date": [], "ratio": []})
        return cls(pd.DataFrame(columns=_WINDOW_COLUMNS), splits, np.array([], "datetime64[D]"), {})

    def window(self, first: date, session: date) -> pd.DataFrame:
        """Bars with ``first <= session_date <= session``, adjusted as of ``session``."""
        lo = int(np.searchsorted(self._days, np.datetime64(first, "D"), side="left"))
        hi = int(np.searchsorted(self._days, np.datetime64(session, "D"), side="right"))
        out = self.frame.iloc[lo:hi]
        later = self.splits[self.splits["ex_date"] > session]
        if later.empty or out.empty:
            return out
        factor = np.ones(hi - lo)
        for iid, ratio in later.groupby("instrument_id")["ratio"].prod().items():
            rows = self._rows[str(iid)]
            factor[rows[(rows >= lo) & (rows < hi)] - lo] *= ratio
        out = out.copy()
        prices = [c for c in _PRICES if c in out.columns]
        out[prices] = out[prices].to_numpy() * factor[:, None]
        if "volume" in out.columns:
            out["volume"] = out["volume"].to_numpy() / factor
        return out


def session_bars(
    reader: StoreReader,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
    columns: Sequence[str] | None = None,
) -> SessionBars:
    """Daily bars for ``start..end`` (split events in the range applied) as ``SessionBars``.
    ``columns``: only those of ``open high low close volume`` are read and kept.

    Raises ``MissingDataError`` when no bars are stored in the range."""
    frame = bars(reader, "1d", start, end, instruments, as_of, columns)
    splits = read_events(reader, "events/split", start, end, instruments, as_of).frame
    no_dividends = pd.DataFrame(columns=["instrument_id", "ts", "cash_amount"])
    frame = adjust_bars(frame, splits, no_dividends, "splits")
    frame = frame[[c for c in _WINDOW_COLUMNS if c in frame.columns]]
    frame = frame.sort_values(["session_date", "instrument_id"], kind="stable")
    frame = frame.reset_index(drop=True)
    table = pd.DataFrame(
        {
            "instrument_id": splits["instrument_id"].astype(str) if len(splits) else [],
            "ex_date": pd.to_datetime(splits["ts"], utc=True).dt.date if len(splits) else [],
            "ratio": splits["ratio"].astype(float) if len(splits) else [],
        }
    )
    days = pd.to_datetime(frame["session_date"]).to_numpy(dtype="datetime64[D]")
    return SessionBars(
        frame,
        table,
        days,
        _rows_of(frame["instrument_id"].astype(str), list(table["instrument_id"])),
    )


# ------------------------------------------------------------------ fixed windows of closes
type DateWindow = tuple[date, date]
WINDOW_PIECE = 60  # sessions read at a time: bounds the raw (uncompacted) frame in memory


def window_closes(
    reader: StoreReader,
    windows: Sequence[DateWindow],
    through: date,
    instruments: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Closes of fixed ``(first, last)`` windows up to ``through``: columns ``window`` (the index
    into ``windows``, int8), ``day`` (datetime64[ns]), ``instrument_id`` (categorical) and
    ``close`` (float64), sorted by ``day`` so that the rows on or before a session are a prefix.

    Each window is read from ``first`` to the earlier of ``last`` and ``through``, only the close
    column, ``WINDOW_PIECE`` sessions at a time, each piece kept compact (a categorical id and
    two numbers per row) before the next is read: years of every instrument are a few hundred
    MB, not the GB of the full bars. Splits with an ex-date inside the window are applied to
    every piece (the later ones are not): all prices of one instrument in a window then share
    one adjustment, so the ratios a caller takes (drawdown, recovery) do not depend on how far
    the read went. A window with no stored bars (before the history we hold) has no rows.
    ``instruments``: only these (dropped after each piece is read: the rest never stays in memory).
    """
    days_of: list[np.ndarray] = []  # per piece: day, window, close and the id categorical
    windows_of: list[np.ndarray] = []
    closes_of: list[np.ndarray] = []
    ids_of: list[Any] = []
    no_dividends = pd.DataFrame(columns=["instrument_id", "ts", "cash_amount"])
    for index, (first, last) in enumerate(windows):
        end = min(last, through)
        if end < first:
            continue
        splits = read_events(reader, "events/split", first, end, instruments).frame
        days = sessions_between(first, end)
        for i in range(0, len(days), WINDOW_PIECE):
            piece = days[i : i + WINDOW_PIECE]
            try:
                frame = bars(reader, "1d", piece[0], piece[-1], None, None, ("close",))
            except MissingDataError:
                continue
            frame = adjust_bars(frame, splits, no_dividends, "splits")
            ids = pd.Categorical(frame["instrument_id"].astype(str))
            wanted = np.ones(len(ids), dtype=bool)
            if instruments is not None:  # on the categories (a few thousand), not on every row
                wanted = ids.categories.isin(list(instruments))[ids.codes]
            days_of.append(
                pd.to_datetime(frame["session_date"]).to_numpy(dtype="datetime64[ns]")[wanted]
            )
            windows_of.append(np.full(int(wanted.sum()), index, dtype=np.int8))
            closes_of.append(frame["close"].to_numpy(dtype=np.float64)[wanted])
            ids_of.append(ids[wanted].remove_unused_categories())
    if not days_of:
        return pd.DataFrame(
            {
                "window": np.array([], dtype=np.int8),
                "day": np.array([], dtype="datetime64[ns]"),
                "instrument_id": pd.Categorical([]),
                "close": np.array([], dtype=np.float64),
            }
        )
    day = np.concatenate(days_of)
    days_of.clear()
    # The rows on or before a session must be a prefix. Windows in date order, as given, already
    # are; otherwise (overlapping or unordered windows) pay for a stable sort.
    order = None if bool(np.all(day[1:] >= day[:-1])) else np.argsort(day, kind="stable")
    day = day if order is None else day[order]
    ids_all = union_categoricals(ids_of)  # one category set, codes kept
    ids_of.clear()
    window = np.concatenate(windows_of)
    windows_of.clear()
    close = np.concatenate(closes_of)  # a column at a time: the pieces are freed as used
    closes_of.clear()
    if order is not None:
        ids_all, window, close = ids_all[order], window[order], close[order]
    columns = {"window": window, "day": day, "instrument_id": ids_all, "close": close}
    return pd.DataFrame(columns, copy=False)
