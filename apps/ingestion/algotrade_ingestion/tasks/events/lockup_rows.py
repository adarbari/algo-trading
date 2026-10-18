"""The rows of ``events/ipo_lockup`` (ADR 0050, edge build D8), built and compared without I/O:
the columns, a prospectus's hit, ``lockup_days`` / ``lockup_expiry`` from the extracted facts and
the ``lockup_dates`` rules, the row of one prospectus (``known_from`` its acceptance session) and
the comparison of a fresh row with the stored one (a changed value is a new version, which the
task dates with ``lockup_dates.restated_known_from``).
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade_ingestion.tasks.events.lockup_dates import (
    DAYS,
    acceptance_session,
    expiry_session,
    restriction_end,
)
from algotrade_sources.framework.series import IPO_EXTRACTED, IPO_RULES_VERSION

RULES_VERSION = IPO_RULES_VERSION  # the extraction rules a stored row was read by

KEY = ["cik", "accession"]
COLUMNS = [
    "instrument_id",
    "ts",
    "known_from",
    "cik",
    "accession",
    "filing_date",
    "issuer_name",
    "primary_document",
    "is_ipo",
    "prospectus_date",
    "ticker",
    "exchange",
    "offer_price",
    "lockup_days",
    "lockup_terms",
    "lockup_expiry",
    "early_release",
    "early_release_text",
    "extraction",
    "reason",
    "rules_version",
]
VALUES = [c for c in COLUMNS if c not in ("known_from",)]  # what a changed row is judged on


@dataclass(frozen=True)
class Hit:
    """One listed 424B4: the issuer's CIK (10 digits), the accession, the filing date, the name."""

    cik: str
    accession: str
    filing_date: date
    name: str | None


def hits_of(frame: pd.DataFrame) -> list[Hit]:
    """The ``HIT_COLUMNS`` frame as hits, oldest filing first."""
    return sorted(
        (
            Hit(
                str(r["cik"]),
                str(r["accession"]),
                pd.Timestamp(r["filing_date"]).date(),
                None if pd.isna(r["name"]) else str(r["name"]),
            )
            for r in frame.to_dict("records")
        ),
        key=lambda h: (h.filing_date, h.accession),
    )


def _norm(value: Any) -> Any:
    """``value`` comparable across a stored and a fresh row: nulls are None, a midnight naive
    timestamp is its date (a date column read back), an instant stays an aware timestamp."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value if value.tzinfo else value.date()
    return float(value) if isinstance(value, float) else value


def same_values(new: dict[str, Any], held: dict[str, Any]) -> bool:
    """Whether ``new`` and ``held`` agree on every column of ``VALUES`` (null equals null)."""
    return all(_norm(new.get(c)) == _norm(held.get(c)) for c in VALUES)


def lockup_fields(facts: dict[str, Any]) -> dict[str, Any]:
    """``lockup_days``, ``lockup_expiry`` and the ``reason`` of a row, from the extracted facts
    and the ``lockup_dates`` rules; null unless a term was extracted (and a date for the expiry)."""
    n, unit, start = facts["lockup_n"], facts["lockup_unit"], facts["prospectus_date"]
    reason = facts["reason"]
    if facts["extraction"] != IPO_EXTRACTED or n is None or pd.isna(n):
        return {"lockup_days": None, "lockup_expiry": None, "reason": reason}
    if start is None or pd.isna(start):
        days = int(n) if unit == DAYS else None
        why = "the text gives no prospectus date, so no expiry date"
        return {"lockup_days": days, "lockup_expiry": None, "reason": why}
    end = restriction_end(start, int(n), unit)
    return {"lockup_days": (end - start).days, "lockup_expiry": expiry_session(end), "reason": None}


def build_row(
    hit: Hit,
    accepted: pd.Timestamp,
    document: str,
    facts: dict[str, Any],
    instrument_id: str | None,
) -> dict[str, Any]:
    """One ``COLUMNS`` row (``known_from`` the acceptance session; a changed version restates)."""
    return {
        "instrument_id": instrument_id,
        "ts": accepted,
        "known_from": acceptance_session(accepted),
        "cik": hit.cik,
        "accession": hit.accession,
        "filing_date": hit.filing_date,
        "issuer_name": hit.name,
        "primary_document": document or None,
        "is_ipo": bool(facts["is_ipo"]),
        "prospectus_date": None if pd.isna(facts["prospectus_date"]) else facts["prospectus_date"],
        "ticker": facts["ticker"],
        "exchange": facts["exchange"],
        "offer_price": None if pd.isna(facts["offer_price"]) else float(facts["offer_price"]),
        "lockup_terms": facts["lockup_terms"],
        "early_release": bool(facts["early_release"]),
        "early_release_text": facts["early_release_text"],
        "extraction": facts["extraction"],
        "rules_version": RULES_VERSION,
        **lockup_fields(facts),
    }


def as_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """``rows`` as a frame of the declared dtypes (``COLUMNS`` order)."""
    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame["lockup_days"] = frame["lockup_days"].astype("Int64")
    frame["offer_price"] = frame["offer_price"].astype("float64")
    for flag in ("is_ipo", "early_release"):
        frame[flag] = frame[flag].astype(bool)
    return frame
