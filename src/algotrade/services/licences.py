"""The one data-licence gate (ADR 0028, ADR 0064 decision 10): which catalogue fields a user
may see values of. A field is read through ``licence_of`` (a stored feature's own
``Feature.licence``, an expression feature's strictest of what it reads: ADR 0023), a user's
``held`` licences come from the users registry (``held_by``: ``open`` for everyone, anything
else only when ``config/site/users.toml`` lists it for that user; a role never grants one),
and ``hidden_fields`` is what every path that serves per-name values removes before it reads:
the read model (``services.read``: values, tables, distributions, stored results), the
Builder's preview and a screener run (``services.selection.fields_view``). A hidden field is
never read, so it is UNKNOWN (``UnknownCode.LICENCE`` in the read model; missing to a screen,
which never passes a hard criterion on a missing value, ADR 0015)."""

from collections.abc import Collection, Iterable

from algotrade.config.site.users import UsersSettings
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import LICENCES, Licence

OPEN: Licence = "open"
PERSONAL: Licence = "personal"
ALL_LICENCES: frozenset[str] = frozenset(LICENCES)  # every licence held: no field is hidden


def held_by(users: UsersSettings, user_id: str) -> frozenset[str]:
    """The licences ``user_id`` holds (``open`` always; an unknown user nothing more)."""
    return frozenset(x for x in LICENCES if users.holds(user_id, x))


def licence_of(features: FeatureSet, field: str) -> str:
    """The licence of a catalogue field (``rollup.<key>.<col>``, ``market.<key>.<col>``,
    ``feature.<name>``); ``open`` for ``instrument.*`` reference facts and for a name the
    catalogue does not resolve (it declares no licence: a stored value of a field since removed
    from the catalogue is not gated)."""
    found = features.feature(field)
    return OPEN if found is None else str(found.licence)


def hidden_fields(
    features: FeatureSet, fields: Iterable[str], held: Collection[str]
) -> frozenset[str]:
    """The ``fields`` whose licence is not in ``held``."""
    return frozenset(f for f in fields if licence_of(features, f) not in held)
