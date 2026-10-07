"""One catalogue of every feature: the code groups, the site expression features, and the
groups that materialise expressions.

``FeatureSet.build(groups, definitions, superseded)``:

- checks every expression (``definitions.build_expressions``) against the code groups;
- turns each ``materialise = true`` expression into a one-feature group ``<name>@v<N>``
  (table ``rollups/instrument/<name>@v<N>``, ``rollups/market/`` for a market-entity one;
  a new expression version is a new table) whose
  compute evaluates the formula over its inputs' rows, so the ``rollups`` task stores it
  after its inputs, and a group may read it like any group (``iv30@v1`` reads ``div_yield``);
- orders all groups by dependency (an unknown dependency or a cycle fails here).

``evaluate(frames, names)`` computes expression features from stored group rows (one
session or a range: ``frame.join``), reading a materialised expression from its table and
computing every other one (virtual) in dependency order; ``stored_columns(names)`` says which
group columns that needs, so a reader loads nothing else. ``moved_field`` maps a field of a
superseded group (``rollup.price_stats@v1.pct_from_high_52w``) to where it lives now.

``with_user(definitions)`` is a user's catalogue (ADR 0023 step 4): this set plus the user's
expression features (``scope == "user"``), checked on top of the site's (never materialised).
"""

from collections.abc import Mapping, Sequence
from datetime import date
from functools import partial

import numpy as np
import pandas as pd

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import rollup_table
from algotrade.features.expressions.definitions import Expression, build_expressions, formula_type
from algotrade.features.expressions.evaluator import (
    KIND_OF,
    evaluate_formula,
    from_column,
    to_column,
)
from algotrade.features.expressions.frame import join
from algotrade.features.expressions.functions import Type
from algotrade.features.framework.columns import conform
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, Superseded
from algotrade.features.framework.feature import Feature, StatusRule
from algotrade.features.framework.graph import dependency_order


class FeatureSet:
    def __init__(
        self,
        code: Mapping[str, FeatureGroup],
        expressions: Mapping[str, Expression],
        superseded: Mapping[str, Superseded],
    ) -> None:
        self.code = dict(code)
        self.expressions = dict(expressions)
        self.superseded = dict(superseded)
        self._by_name = {g.name: g for g in self.code.values()}
        materialised = [self._materialised(e) for e in self.expressions.values() if e.materialise]
        try:
            ordered = dependency_order([*self.code.values(), *materialised])
        except ValueError as exc:
            raise ConfigurationError(
                f"{exc} (a group reads an expression feature only when it is declared with "
                "materialise = true in config/site/features)"
            ) from exc
        self.groups: dict[str, FeatureGroup] = {g.key: g for g in ordered}
        self.features: dict[str, Feature] = {
            f.key: f for g in self.code.values() for f in g.features
        } | {e.feature.key: e.feature for e in self.expressions.values()}
        self._by_field = {f.field: f for f in self.features.values()}
        self._check_statuses()

    def _check_statuses(self) -> None:
        """A ``null_status`` naming another group's column (``<group>.<col>@vN``) must name a
        declared one (ADR 0042)."""
        for f in self.features.values():
            if "@" not in f.null_status:
                continue
            group, _, rest = f.null_status.partition(".")
            owner = self.code.get(f"{group}@{rest.partition('@')[2]}")
            if owner is None or rest.partition("@")[0] not in owner.columns:
                raise ConfigurationError(
                    f"{f.key}: null_status {f.null_status!r} is not a declared feature column"
                )

    @classmethod
    def build(
        cls,
        groups: Mapping[str, FeatureGroup],
        definitions: Sequence[FeatureDefinition] = (),
        superseded: Mapping[str, Superseded] | None = None,
    ) -> "FeatureSet":
        return cls(groups, build_expressions(definitions, groups), superseded or {})

    def with_user(self, definitions: Sequence[FeatureDefinition]) -> "FeatureSet":
        """This set plus a user's expression features (virtual; they may name this set's
        expressions but not take their names). ``self`` when there are none."""
        if not definitions:
            return self
        stored = [d.where for d in definitions if d.owner is None or d.materialise]
        if stored:
            raise ConfigurationError(f"{stored[0]}: not a (virtual) user feature")
        added = build_expressions(definitions, self.code, base=self.expressions)
        return FeatureSet(self.code, {**self.expressions, **added}, self.superseded)

    def formula_type(self, expr: str, where: str = "expr") -> Type:
        """The type of a free-standing formula over this catalogue (``ExpressionError``)."""
        return formula_type(expr, self.code, self.expressions, where)

    # ------------------------------------------------------------------ lookups
    def feature(self, name: str) -> Feature | None:
        """By key (``price_stats.hv30@v2``, ``near_52w@v1``), selection field
        (``rollup.price_stats@v2.hv30``, ``feature.near_52w``) or expression name."""
        if name in self.expressions:
            return self.expressions[name].feature
        return self.features.get(name) or self._by_field.get(name)

    def field_types(self, entity: str | None = None) -> dict[str, str]:
        """Every selectable feature field (of ``entity`` only, when given) -> its dtype."""
        return {
            f.field: f.dtype for f in self.features.values() if entity is None or f.entity == entity
        }

    def table(self, name: str) -> str:
        """The stored table of a code group or a materialised expression (by name)."""
        if name in self._by_name:
            return self._by_name[name].table
        e = self.expressions[name]
        return rollup_table(e.feature.entity, f"{e.name}@v{e.feature.version}")

    def applicability(self, name: str) -> tuple[frozenset[str], tuple[StatusRule, ...]]:
        """What a value's absence may be put down to (ADRs 0042, 0046), inherited by an
        expression from everything it reads like its licence: -> (the non-``any``
        ``applies_to`` values of the stored features it reads, each ``null_status`` field with
        its ``illiquid_statuses``, ``explained_statuses`` and the declaring feature's table).
        ``name``: a selection field (``rollup.<group>.<col>``, ``feature.<name>``)."""
        applies: set[str] = set()
        statuses: list[StatusRule] = []

        def add(feature: Feature) -> None:
            if feature.applies_to != "any":
                applies.add(feature.applies_to)
            if feature.null_status:
                statuses.append(
                    (
                        feature.status_field,
                        frozenset(feature.illiquid_statuses),
                        frozenset(feature.explained_statuses),
                        rollup_table(feature.entity, feature.group),
                    )
                )

        def visit(expression: str) -> None:
            e = self.expressions[expression]
            for ref in e.refs:
                group, _, column = ref.partition(".")
                if group in self._by_name:
                    add(self._by_name[group].feature(column))
            for dep in e.uses:
                visit(dep)

        if name.startswith("feature."):
            visit(name.removeprefix("feature."))
        else:
            found = self.feature(name)
            if found is not None:
                add(found)
        return frozenset(applies), tuple(dict.fromkeys(statuses))

    def moved_field(self, name: str) -> str | None:
        """Where a field of a superseded group lives now (``""``: retired); ``None`` when
        ``name`` is not such a field."""
        head, _, rest = name.partition(".")
        key, _, column = rest.rpartition(".")
        if head != "rollup" or key not in self.superseded:
            return None
        old = self.superseded[key]
        if column in old.fields:
            return old.fields[column]
        if column in self.expressions:
            return f"feature.{column}"
        by = self.code.get(old.by)
        return f"rollup.{old.by}.{column}" if by is not None and column in by.columns else ""

    # ------------------------------------------------------------------ evaluation
    def plan(
        self, names: Sequence[str], compute: Sequence[str] = ()
    ) -> tuple[dict[str, set[str]], list[str]]:
        """-> (stored columns to read, by group or materialised expression name; the
        expressions to compute, in dependency order). A materialised expression is read
        from its table unless it is in ``compute``."""
        stored: dict[str, set[str]] = {}
        todo: list[str] = []

        def visit(name: str) -> None:
            e = self.expressions[name]
            if e.materialise and name not in compute:
                stored.setdefault(name, set()).add(name)
                return
            for ref in e.refs:
                group, _, column = ref.partition(".")
                stored.setdefault(group, set()).add(column)
            for group in e.exists:
                stored.setdefault(group, set())
            for dep in e.uses:
                visit(dep)
            if name not in todo:
                todo.append(name)

        for name in names:
            if name not in self.expressions:
                raise KeyError(
                    f"unknown expression feature {name!r}; known: {sorted(self.expressions)}"
                )
            visit(name)
        return stored, todo

    def stored_columns(self, names: Sequence[str]) -> dict[str, set[str]]:
        """Stored table -> the columns ``names`` need (empty set: only row presence)."""
        stored, _ = self.plan(names)
        return {self.table(group): columns for group, columns in stored.items()}

    def _kind(self, ref: str) -> str:
        group, _, column = ref.partition(".")
        if group in self.expressions:
            return KIND_OF[self.expressions[group].feature.dtype]
        return KIND_OF[self._by_name[group].feature(column).dtype]

    def evaluate(
        self,
        frames: Mapping[str, pd.DataFrame | None],
        names: Sequence[str],
        compute: Sequence[str] = (),
    ) -> pd.DataFrame:
        """``names`` over stored rows -> ``session_date``, ``instrument_id`` + one typed
        column per name. ``frames``: rows by stored table (``stored_columns``)."""
        stored, todo = self.plan(names, compute)
        by_group = {g: frames.get(self.table(g)) for g in stored}
        keys, columns = join(by_group, stored)
        values: dict[str, tuple[np.ndarray, str]] = {}

        def lookup(name: str) -> tuple[np.ndarray, str]:
            if name not in values:
                if name.startswith("exists:"):
                    values[name] = (np.asarray(columns[name], dtype=float), "bool")
                elif "." in name:
                    kind = self._kind(name)
                    values[name] = (to_column(columns[name], kind), kind)
                else:  # a materialised expression, read from its table
                    kind = KIND_OF[self.expressions[name].feature.dtype]
                    values[name] = (to_column(columns[f"{name}.{name}"], kind), kind)
            return values[name]

        for name in todo:
            values[name] = evaluate_formula(self.expressions[name].node, lookup, len(keys))
        typed = pd.DataFrame({"instrument_id": keys["instrument_id"].astype(str).to_numpy()})
        for name in names:
            typed[name] = from_column(*lookup(name)).to_numpy()
        dtypes = {n: self.expressions[n].feature.dtype for n in names}
        out = conform("expressions", typed, dtypes)
        out.insert(0, "session_date", keys["session_date"].to_numpy())
        return out

    # ------------------------------------------------------------------ materialised
    def _materialised(self, e: Expression) -> FeatureGroup:
        stored, _ = self.plan([e.name], compute=[e.name])
        tables = {self.table(g): g for g in sorted(stored)}
        return FeatureGroup(
            e.name,
            e.feature.version,
            f"Materialised expression feature {e.name} ({e.definition.where})",
            tuple(Input(t, required=False) for t in tables),
            (e.feature,),
            partial(_compute_materialised, self, e.name),
            entity=e.feature.entity,
        )


def _compute_materialised(
    features: FeatureSet, name: str, inputs: Inputs, session: date, params: None
) -> pd.DataFrame:
    """A materialised expression for one session, from its inputs' rows for the session."""
    out = features.evaluate(inputs, [name], compute=[name])
    return out[out["session_date"] == session].drop(columns="session_date")
