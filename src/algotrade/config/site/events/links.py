"""The macro release links (``config/site/events/links.toml``): per release key (the keys of
``releases.toml``) the agency's page for that release, shown as the link of its row in the
event list under the Explore chart. The loader checks shape, the key spelling and that every
address is a plain ``https`` URL (no credentials, query, fragment or whitespace); that the keys
are releases that exist is checked by a fitness test, since the two files are separate."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

FOLDER = "events"
NAME = "links"
_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
_URL = re.compile(r"^https://[a-z0-9-]+(\.[a-z0-9-]+)+(/[A-Za-z0-9._~/-]*)?$")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class EventLinks:
    """``links.toml``: release key -> the agency's page (none without the file)."""

    macro: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "EventLinks":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("macro",))
        raw = root.raw("macro") or {}
        if not isinstance(raw, Mapping):
            raise ConfigurationError(f"{where} macro: expected a table (KEY = url)")
        for key, url in raw.items():
            if not _KEY.match(str(key)):
                raise ConfigurationError(f"{where} macro: expected {_KEY.pattern}, got {key!r}")
            if not isinstance(url, str) or not _URL.match(url):
                raise ConfigurationError(f"{where} macro {key}: expected an https URL, got {url!r}")
        return cls(dict(raw))


def load_event_links(configs: Documents) -> EventLinks:
    """``config/site/events/links.toml``; missing: no links."""
    return EventLinks.from_document(configs.load("site", FOLDER, NAME))
