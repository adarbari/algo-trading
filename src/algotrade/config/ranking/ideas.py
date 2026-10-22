"""``IdeasRule``: the parameters of the Ideas ranking rule from ``config/site/ranking/ideas.toml``
(owner decision 2026-10-22): how many picks each kind of screener contributes and how much a
viewer's own screener weighs. Site only, fail closed: an unknown key, a wrong type or a value
below 1 names the file. ``hash`` identifies the rule in a cursor and, later, a stored list's
stamp: a changed parameter is a new rule."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table

KIND = "ranking"
NAME = "ideas"
WHERE = "ideas.toml"


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class IdeasRule:
    """``site_top`` / ``user_top``: the first picks of a site preset / the viewer's own screener
    that count; ``user_weight``: a pick's weight for the viewer's own screener (a site preset's
    is 1)."""

    site_top: int = 5
    user_top: int = 20
    user_weight: int = 3

    @property
    def hash(self) -> str:
        """Twelve hex digits of the parameters' canonical JSON."""
        text = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode()).hexdigest()[:12]


def parse_ideas_rule(doc: Mapping[str, Any] | None, where: str = WHERE) -> IdeasRule:
    """The document, typed; a missing file is the shipped default."""
    d = IdeasRule()
    t = Table(doc, where)
    t.only(("site_top", "user_top", "user_weight"))
    return IdeasRule(
        site_top=t.integer("site_top", d.site_top, 1),
        user_top=t.integer("user_top", d.user_top, 1),
        user_weight=t.integer("user_weight", d.user_weight, 1),
    )


def load_ideas_rule(configs: Documents) -> IdeasRule:
    """The site's Ideas ranking rule (``config/site/ranking/ideas.toml``)."""
    return parse_ideas_rule(configs.load("site", KIND, NAME))
