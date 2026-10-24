"""``fields_without_data``: the catalogue fields no instrument has a known value of for the read
session (decision log 2026-10-24 "Cohort / IV-rank percentile filters"). A filter on such a field
can only match zero rows, so ``filterSet`` serves it as withheld (``NOT_STORED``) instead of
offering a control that erodes trust (the lists still read an input that names it). It returns
by itself once the session has data: an IV-rank percentile needs about 60 sessions of IV history,
a cohort rank the universe and company snapshots. One read of the whole population for every
field of a surface, kept per published version, session and licence set. A field the viewer's
licences do not cover is never read here (it is withheld as ``LICENCE`` first), and an empty
population withholds nothing."""

from collections.abc import Iterable

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.features import load_feature_values


def _known(ctx: ReadContext, fields: tuple[str, ...]) -> dict[str, tuple[bool, bool]]:
    """``{field: (population is not empty, some instrument has a known value)}``, one read of
    the whole population for every field of the surface, kept per published version, session
    and licence set (``load_feature_values`` bars a field the licences do not cover)."""

    def read() -> dict[str, tuple[bool, bool]]:
        found = load_feature_values(ctx, None, list(fields))
        return {
            f: (bool(found), any(v[k].value is not None for v in found.values()))
            for k, f in enumerate(fields)
        }

    key = (
        "filter-known",
        ctx.reader.version(),
        ctx.session.date,
        tuple(sorted(ctx.licences)),
        fields,
    )
    known: dict[str, tuple[bool, bool]] = ctx.cache.get_or_compute(key, read)
    return known


def fields_without_data(ctx: ReadContext, fields: Iterable[str]) -> frozenset[str]:
    """The ``fields`` with a non-empty population in which every value is UNKNOWN."""
    asked = tuple(dict.fromkeys(fields))
    if not asked:
        return frozenset()
    return frozenset(
        f for f, (populated, known) in _known(ctx, asked).items() if populated and not known
    )
