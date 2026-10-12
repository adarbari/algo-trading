"""The payload of a ``formula_accepted`` event: the saved user feature's formula, its fingerprint
(``features.expressions.fingerprint``: the key an admin groups equal formulas by), unit and
description, bounded. Pure over the user's own saved feature definitions; a feature that is not
there or does not parse yields the subject-only payload, never an error (the request that saved
it must not fail on its feedback). The formula text is strategy content: it is read back only by
the admin loader (``services/read/formulas``) and nulled by retain and erase with the rest of
the payload (``feedback.retention``)."""

from collections.abc import Sequence
from typing import Any

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.completion import clip
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.fingerprint import fingerprint

MAX_EXPRESSION = 1000  # characters of the formula, its canonical form and the description kept
MAX_DESCRIPTION = 500
DRAFT_PREFIX = "draft_"  # the name Describe it proposes a formula under


def accepted_payload(
    subject: str,
    feature: str | None,
    saved: Sequence[FeatureDefinition],
    proposed: str | None = None,
) -> dict[str, Any]:
    """``{"subject", "picked"}`` plus, when ``feature`` is one of the user's ``saved`` features
    that parses and is the formula proposed for ``subject``: ``feature``, ``expression``,
    ``fingerprint``, ``canonical``, ``unit``, ``description``. "Is the proposed formula": its
    fingerprint equals the proposal's ``proposed`` one when that is known, else the name is the
    subject or a ``draft_`` one (the client names the feature; it is never trusted further)."""
    payload: dict[str, Any] = {"subject": subject, "picked": None}
    if not feature:
        return payload
    try:
        for definition in saved:
            if definition.name != feature:
                continue
            found = fingerprint(definition)
            if proposed:
                if found.hash != proposed:
                    break
            elif feature != subject and not feature.startswith(DRAFT_PREFIX):
                break
            return payload | {
                "feature": feature,
                "expression": clip(" ".join(definition.expr.split()), MAX_EXPRESSION),
                "fingerprint": found.hash,
                "canonical": clip(found.text, MAX_EXPRESSION),
                "unit": clip(definition.unit, 40),
                "description": clip(definition.description, MAX_DESCRIPTION),
            }
    except (ConfigurationError, ValueError, TypeError, AttributeError):
        pass  # not a feature we can read: the event is recorded as before
    return payload
