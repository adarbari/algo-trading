"""How a user evaluates edges (ADR 0053 amendment, ED5a; ADR 0015 layering): ``EvaluationSettings``
from ``config/users/<id>/evaluation.toml`` over the site default, which is none: an edge's own
``frozen_from`` is the site's split. ``split_from`` is the first session of the test slice; a
run's ``--split-from`` goes over both. A split other
than an edge's ``frozen_from`` makes the run exploratory (the harness decides, not this
module)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from algotrade.config.site.fields import Table
from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import ConfigurationError

KIND = "evaluation"  # users/<id>/evaluation.toml
KEYS = ("split_from",)


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class EvaluationSettings:
    split_from: date | None = None  # None: each edge's frozen_from is the split


def parse_evaluation(doc: Mapping[str, Any] | None, where: str) -> EvaluationSettings:
    """One layer's document, typed; an unknown key or a bad date names ``where``."""
    t = Table(doc, where)
    t.only(KEYS)
    raw = t.raw("split_from")
    if raw is None or type(raw) is date:
        return EvaluationSettings(raw)
    try:
        if isinstance(raw, str):
            return EvaluationSettings(date.fromisoformat(raw))
    except ValueError:
        pass
    raise ConfigurationError(f"{where} split_from: expected a date (2026-04-01), got {raw!r}")


def load_evaluation(configs: Documents, user: str = SITE_USER) -> EvaluationSettings:
    """The user's ``evaluation.toml`` over the site default (none); the site user has no file."""
    if user == SITE_USER:
        return EvaluationSettings()
    return parse_evaluation(configs.load(user, KIND, KIND), f"users/{user}/evaluation.toml")
