"""The rows a fetched series adds to ``macro/series`` (ADR 0048): the vintage rule, then a diff
against what is stored. Pure frames in, frames out; the ``macro`` task writes the result.

``vintage_rows`` gives each fetched value its vintage:

- ``pit = "alfred"``: the row keeps ALFRED's ``realtime_start`` and is ``alfred``. The rows an
  observation has at the series' FIRST vintage that are older than the series' release lag
  (observations before ALFRED's archive begins) have no real vintage date: they take the
  ``lagged`` rule (``data.macro.vintages``), which says which values relied on it;
- ``pit = "lag"``: one value per observation (the current one; a published file has only
  that) with ``vintage_date = obs_date + release_lag_days``, ``lagged``.

``rows_to_write`` keeps only what the table does not already hold, so a rerun on unchanged
data writes nothing:

- an ``alfred`` row is a key (id, observation, vintage) a vintage never changes: written when
  the key is new (or, were ALFRED to correct one, when its value differs);
- a ``lagged`` row is a key whose value CAN change (a source corrects a number): when the
  stored value differs, the new one is a NEW vintage dated the run's session, never an
  overwrite, so a session before the run still sees the old value. The one exception: the
  stored vintage is itself dated after the session (an observation not public yet), which no
  session has read, so the corrected value takes that key.

Values are stored as published (the registry's ``transform`` is how the macro feature group
reads them, not an ingestion step).
"""

from datetime import date

import pandas as pd

from algotrade.config.site.macro import MacroSeries
from algotrade.data.macro.vintages import lagged_vintages
from algotrade.storage.tables.schemas import ALFRED, LAGGED

COLUMNS = ["instrument_id", "series", "obs_date", "vintage_date", "value", "vintage_kind"]
DAY_KEY = ["instrument_id", "obs_date"]
KEY = [*DAY_KEY, "vintage_date"]


def vintage_rows(spec: MacroSeries, fetched: pd.DataFrame) -> pd.DataFrame:
    """``fetched`` (``SERIES_COLUMNS``) as ``COLUMNS`` rows for ``spec``: dates as ``date``,
    the vintage rule applied, sorted by observation then vintage."""
    frame = fetched[fetched["obs_date"].notna()]
    if spec.pit == "lag":
        current = frame.sort_values("vintage_date", kind="stable", na_position="first")
        parts = [
            lagged_vintages(current.drop_duplicates("obs_date", keep="last"), spec.release_lag_days)
        ]
    else:
        parts = _alfred_parts(spec, frame)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLUMNS)
    out["instrument_id"] = spec.instrument_id
    out["series"] = spec.vendor_code
    for column in ("obs_date", "vintage_date"):
        out[column] = pd.to_datetime(out[column]).dt.date
    out["value"] = out["value"].astype("float64")
    return (
        out.reindex(columns=COLUMNS)
        .sort_values(["obs_date", "vintage_date"], kind="stable")
        .reset_index(drop=True)
    )


def _alfred_parts(spec: MacroSeries, frame: pd.DataFrame) -> list[pd.DataFrame]:
    """The ALFRED rows as ``alfred``, except those of the first vintage (and rows with no
    vintage date) that were public before it: ``lagged``."""
    if frame.empty:
        return []
    first = frame["vintage_date"].min()
    before = pd.to_datetime(frame["obs_date"]) + pd.Timedelta(days=spec.release_lag_days) < first
    undated = frame["vintage_date"].isna()
    lagged = (frame["vintage_date"] == first) & before | undated
    parts = [frame[~lagged].assign(vintage_kind=ALFRED)]
    if lagged.any():
        parts.append(
            lagged_vintages(frame[lagged].drop(columns="vintage_date"), spec.release_lag_days)
        )
    return [p for p in parts if not p.empty]


def _same(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a == b) | (a.isna() & b.isna())


def _as_dates(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in ("obs_date", "vintage_date"):
        out[column] = pd.to_datetime(out[column])
    return out


def rows_to_write(target: pd.DataFrame, stored: pd.DataFrame, session: date) -> pd.DataFrame:
    """The rows of ``target`` (``vintage_rows``) the table needs, given ``stored`` (its
    ``COLUMNS`` for the same series; ``data.macro.series.stored_vintages``): none when nothing
    changed. ``COLUMNS``, dates as ``date``."""
    if target.empty:
        return target
    wanted, held = _as_dates(target), _as_dates(stored)
    new = pd.concat(
        [
            _new_alfred(wanted[wanted["vintage_kind"] == ALFRED], held),
            _changed_lagged(wanted[wanted["vintage_kind"] == LAGGED], held, session),
        ],
        ignore_index=True,
    )
    for column in ("obs_date", "vintage_date"):
        new[column] = new[column].dt.date
    return (
        new.reindex(columns=COLUMNS)
        .sort_values(["obs_date", "vintage_date"], kind="stable")
        .reset_index(drop=True)
    )


def _new_alfred(rows: pd.DataFrame, held: pd.DataFrame) -> pd.DataFrame:
    """``rows`` whose key is not stored, or is stored with another value."""
    if rows.empty:
        return rows
    kept = held[[*KEY, "value"]].rename(columns={"value": "held"})
    merged = rows.merge(kept, on=KEY, how="left", indicator=True)
    unchanged = (merged["_merge"] == "both") & _same(merged["value"], merged["held"])
    return merged[~unchanged].drop(columns=["held", "_merge"])


def _changed_lagged(rows: pd.DataFrame, held: pd.DataFrame, session: date) -> pd.DataFrame:
    """``rows`` with no stored ``lagged`` vintage of the observation, or whose value differs
    from the newest one: those become the new vintage (dated ``session``, see the module)."""
    if rows.empty:
        return rows
    lagged = held[held["vintage_kind"] == LAGGED].sort_values("vintage_date", kind="stable")
    newest = lagged.drop_duplicates(DAY_KEY, keep="last")[[*KEY, "value"]]
    newest = newest.rename(columns={"vintage_date": "held_vintage", "value": "held"})
    merged = rows.merge(newest, on=DAY_KEY, how="left")
    unchanged = merged["held_vintage"].notna() & _same(merged["value"], merged["held"])
    changed = merged[~unchanged].copy()
    today, stored_on = pd.Timestamp(session), changed["held_vintage"]
    corrected = stored_on.where(stored_on.isna() | (stored_on >= today), today)  # the later one
    changed["vintage_date"] = corrected.fillna(changed["vintage_date"])
    return changed.drop(columns=["held", "held_vintage"])


def vintage_count(stored: pd.DataFrame, written: pd.DataFrame) -> int:
    """How many vintages the table holds for a series once ``written`` is stored."""
    keys = pd.concat([stored[KEY], written[KEY]], ignore_index=True)
    return len(keys.drop_duplicates())
