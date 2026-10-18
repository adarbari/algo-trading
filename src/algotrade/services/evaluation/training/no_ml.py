"""The no-ML guard of the training frame: a learned scorer is never fitted on a feature computed
from a table whose source bars machine learning (``schemas.NO_ML_TABLES``, ``no_ml = true`` in
``architecture/tables.toml``: FINRA's short interest and short-sale volume, whose website terms
exclude "machine learning, neural network, ... predictive analytics").

Rule screens over those tables are allowed (a person writes the rule); a fitted scorer is not.
The check follows each scorer field through the expression features it uses to the stored tables
its groups read (``discovery.frame.feature_reads``), so a formula over a restricted feature is
refused too. A field the catalogue does not resolve is refused as well (fail closed: its inputs
are unknown), except the ``instrument.*`` reference facts.
"""

from collections.abc import Iterable

from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.evaluation.discovery.frame import feature_reads
from algotrade.storage.tables.schemas import NO_ML_TABLES

REFERENCE_FACTS = "instrument"  # ``instrument.*`` fields are reference facts, never restricted


def no_ml_reads(features: FeatureSet, fields: Iterable[str]) -> dict[str, list[str]]:
    """``{field: [no_ml tables it reads]}`` for the fields that read one (an unresolvable field
    maps to an empty list: refused, but names no table)."""
    found: dict[str, list[str]] = {}
    for field in fields:
        feature = features.feature(field)
        if feature is None:
            if field.partition(".")[0] != REFERENCE_FACTS:
                found[field] = []
            continue
        tables = sorted(feature_reads(features, feature).tables & NO_ML_TABLES)
        if tables:
            found[field] = tables
    return found


def refuse_no_ml(features: FeatureSet, fields: Iterable[str], edge_id: str) -> None:
    """Raise ``ConfigurationError`` when a scorer field reads a no_ml table or is unresolvable."""
    bad = no_ml_reads(features, fields)
    if not bad:
        return
    detail = "; ".join(f"{f} ({', '.join(t) or 'unknown inputs'})" for f, t in sorted(bad.items()))
    raise ConfigurationError(
        f"edge {edge_id}: a learned scorer cannot be fitted on {detail}: the source's terms bar "
        "machine learning over its data (no_ml tables); use it in a rule screen instead"
    )
