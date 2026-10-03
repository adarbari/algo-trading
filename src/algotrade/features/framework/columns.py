"""Type a rollup's output by its declaration, so the stored types come from one place.

``conform`` returns ``instrument_id`` plus exactly the declared columns, in declared order,
each cast to the pandas dtype that stores as the declared type (``float32`` -> float32,
``int`` -> int64, ``date`` -> date32, ...) even when every value is null. A declared column
the compute left out is all null (UNKNOWN); an undeclared one is an error, as is a value
that does not fit its type.
"""

from collections.abc import Mapping

import pandas as pd

from algotrade.core.model.errors import DataValidationError


def _cast(values: pd.Series, kind: str) -> pd.Series:
    """One column as its declared type (Arrow-backed where nulls must keep the type)."""
    if kind == "float":
        return pd.to_numeric(values, errors="raise").astype("float64")
    if kind == "float32":
        return pd.to_numeric(values, errors="raise").astype("float32")
    if kind == "int":
        return pd.to_numeric(values, errors="raise").astype("int64[pyarrow]")
    if kind == "date":
        return pd.to_datetime(values, utc=True).dt.date.astype("date32[pyarrow]")
    present = values.where(values.notna(), None)
    if kind == "bool":
        return present.astype("bool[pyarrow]")
    return present.astype("string[pyarrow]")


def conform(table: str, frame: pd.DataFrame, columns: Mapping[str, str]) -> pd.DataFrame:
    """``frame`` with ``instrument_id`` + the declared ``columns``, typed. Raises
    ``DataValidationError`` naming the column that does not fit."""
    extra = sorted(set(frame.columns) - {"instrument_id", *columns})
    if extra:
        raise DataValidationError(table, [f"undeclared columns {extra}: declare them"])
    if "instrument_id" not in frame.columns:
        raise DataValidationError(table, ["missing instrument_id"])
    out = pd.DataFrame({"instrument_id": frame["instrument_id"].astype(str).to_numpy()})
    problems = []
    for name, kind in columns.items():
        values = (
            frame[name].reset_index(drop=True)
            if name in frame.columns
            else pd.Series([None] * len(frame), dtype=object)
        )
        try:
            out[name] = _cast(values, kind)
        except (ValueError, TypeError) as exc:
            problems.append(f"{name}: not a {kind} column ({exc})")
    if problems:
        raise DataValidationError(table, problems)
    return out
