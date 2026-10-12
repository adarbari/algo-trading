"""The payload of a ``formula_accepted`` event: the saved user feature's formula, its fingerprint
(``features.expressions.fingerprint``: the key an admin groups equal formulas by), unit and
description, bounded. Pure over the user's own saved feature documents; a feature that is not
there or does not parse yields the subject-only payload, never an error (the request that saved
it must not fail on its feedback). The formula text is strategy content: it is read back only by
the admin loader (``services/read/formulas``) and nulled by retain and erase with the rest of
the payload (``feedback.retention``)."""

from collections.abc import Mapping
from typing import Any

from algotrade.config.site.features.definitions import feature_definitions
from algotrade.core.model.completion import clip
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.fingerprint import fingerprint

MAX_EXPRESSION = 1000  # characters of the formula, its canonical form and the description kept
MAX_DESCRIPTION = 500


def accepted_payload(
    subject: str,
    user: str,
    feature: str | None,
    docs: Mapping[str, Mapping[str, Any] | None],
) -> dict[str, Any]:
    """``{"subject", "picked"}`` plus, when ``feature`` is a section of one of the user's
    feature documents ``docs`` (theme -> document) that parses: ``feature``, ``expression``,
    ``fingerprint``, ``canonical``, ``unit``, ``description``."""
    payload: dict[str, Any] = {"subject": subject, "picked": None}
    if not feature:
        return payload
    try:
        for theme, doc in docs.items():
            if doc and feature in doc:
                (definition,) = feature_definitions({theme: {feature: doc[feature]}}, user)
                found = fingerprint(definition)
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
