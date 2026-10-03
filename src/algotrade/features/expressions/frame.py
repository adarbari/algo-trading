"""Join stored feature-group rows into the columns an expression is evaluated over.

``join(frames)`` takes each group's rows (``session_date``, ``instrument_id`` + feature
columns; ``None`` when the group has none) and returns the row keys, one row per
(session, instrument) present in ANY of the groups, sorted, plus aligned columns:

    <group>.<column>   the group's value for the row (null when the group has no row for it)
    exists:<group>     1.0 when the group has a row for it, 0.0 when the group has rows for
                       that session but not this instrument, null (NaN) when the group has no
                       rows at all for that session (unknown: not computed, not "absent")

Instruments without a row in any group are not rows: an expression over them is null. Keys
are aligned as integer codes (sessions x instruments), so a two-year range of every
instrument joins in about a second.
"""

from collections.abc import Collection, Mapping

import numpy as np
import pandas as pd

KEYS = ["session_date", "instrument_id"]


def _empty(columns: Mapping[str, Collection[str]]) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    keys = pd.DataFrame({"session_date": [], "instrument_id": []})
    out: dict[str, np.ndarray] = {f"exists:{g}": np.array([]) for g in columns}
    out |= {f"{g}.{c}": np.array([], dtype=object) for g, cs in columns.items() for c in cs}
    return keys, out


def _scatter(values: pd.Series, at: np.ndarray, n: int) -> np.ndarray:
    """``values`` placed at rows ``at`` of ``n`` rows; null elsewhere. Floats stay floats;
    anything else becomes objects with ``None`` (through its distinct values: fast for
    labels)."""
    if values.dtype.kind == "f" and isinstance(values.dtype, np.dtype):
        out = np.full(n, np.nan, dtype=values.dtype)
        out[at] = values.to_numpy()
        return out
    codes, distinct = pd.factorize(values, use_na_sentinel=True)
    lookup = np.empty(len(distinct) + 1, dtype=object)
    lookup[:-1] = np.asarray(distinct, dtype=object)
    lookup[-1] = None  # code -1: null, or no row
    picked = np.full(n, -1, dtype=np.int64)
    picked[at] = codes
    return lookup[picked]


def join(
    frames: Mapping[str, pd.DataFrame | None], columns: Mapping[str, Collection[str]]
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """-> (row keys, ``{"<group>.<column>": values, "exists:<group>": 1 / 0 / NaN}``) for
    the ``columns`` wanted of each group in ``frames`` (by group name)."""
    present = {g: f for g, f in frames.items() if f is not None and len(f)}
    if not present:
        return _empty(columns)
    days, day_names = pd.factorize(
        pd.concat([f["session_date"] for f in present.values()], ignore_index=True), sort=True
    )
    ids, id_names = pd.factorize(
        pd.concat([f["instrument_id"].astype(str) for f in present.values()], ignore_index=True),
        sort=True,
    )
    width = max(len(id_names), 1)
    codes = days.astype(np.int64) * width + ids
    seen = np.zeros(len(day_names) * width, dtype=bool)
    seen[codes] = True
    rows = np.flatnonzero(seen)  # sorted: by session, then instrument
    keys = pd.DataFrame(
        {"session_date": np.asarray(day_names)[rows // width],
         "instrument_id": np.asarray(id_names)[rows % width]}
    )  # fmt: skip
    row_day = rows // width
    out: dict[str, np.ndarray] = {}
    start = 0
    spans = {}
    for group, frame in present.items():
        spans[group] = slice(start, start + len(frame))
        start += len(frame)
    for group, wanted in columns.items():
        if group not in present:
            for column in wanted:
                out[f"{group}.{column}"] = np.full(len(rows), None, dtype=object)
            out[f"exists:{group}"] = np.full(len(rows), np.nan)
            continue
        frame, span = present[group], spans[group]
        at = np.searchsorted(rows, codes[span])
        for column in wanted:
            out[f"{group}.{column}"] = _scatter(frame[column].reset_index(drop=True), at, len(rows))
        found = np.zeros(len(rows), dtype=bool)
        found[at] = True
        has_rows = np.zeros(len(day_names), dtype=bool)
        has_rows[days[span]] = True
        covered = has_rows[row_day]
        out[f"exists:{group}"] = np.where(found, 1.0, np.where(covered, 0.0, np.nan))
    return keys, out
