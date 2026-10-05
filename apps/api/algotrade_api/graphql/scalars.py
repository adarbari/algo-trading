"""The custom scalars of the graph (ADR 0037): ``FeatureName`` (a catalogue field name,
``instrument.<col>``, ``rollup.<group>@vN.<col>`` or ``feature.<name>``), with ``Date`` and
``JSON`` from Strawberry. ``FeatureName`` checks the form when the request is parsed; whether
the caller's catalogue has the name is checked when it is read (``UNKNOWN_FEATURE``)."""

import re
from typing import NewType

import strawberry
from strawberry.types.scalar import ScalarDefinition

FeatureName = NewType("FeatureName", str)

_FORM = re.compile(
    r"^(instrument\.[a-z][a-z0-9_]*"
    r"|rollup\.[a-z][a-z0-9_]*@v[1-9][0-9]*\.[a-z][a-z0-9_]*"
    r"|feature\.[a-z][a-z0-9_]*)$"
)


def parse_feature_name(value: object) -> FeatureName:
    """``value`` as a ``FeatureName``; ``ValueError`` naming it when it is not one."""
    if not isinstance(value, str) or not _FORM.match(value):
        raise ValueError(
            f"{value!r} is not a feature name: instrument.<column>, "
            "rollup.<group>@v<N>.<column> or feature.<name>"
        )
    return FeatureName(value)


SCALARS: dict[object, ScalarDefinition] = {
    FeatureName: strawberry.scalar(
        name="FeatureName",
        description=(
            "A catalogue field: instrument.<column>, rollup.<group>@v<N>.<column> or "
            "feature.<name> (docs/data/features.md)"
        ),
        serialize=str,
        parse_value=parse_feature_name,
    )
}
